//! Oathbox contract.
//!
//! A founder commits a data room's root hash once (immutable). Every answer the
//! TEE gives about that room becomes a receipt, and a receipt is only accepted
//! if it names the same root that was committed. Only the room owner, or a
//! backend account the owner allow-lists, can write receipts.
//!
//! Callers pay for the storage they add: attach a deposit, the exact storage
//! cost is kept and the rest is refunded in the same transaction.

use near_sdk::json_types::U64;
use near_sdk::serde_json::json;
use near_sdk::store::{LookupMap, Vector};
use near_sdk::{env, near, require, AccountId, BorshStorageKey, NearToken, PanicOnDefault, Promise};

const MAX_ID_LEN: usize = 64;
const MAX_MODEL_LEN: usize = 128;
const MAX_BACKENDS: usize = 5;
const MAX_PAGE: u64 = 50;

#[near(serializers = [borsh])]
#[derive(BorshStorageKey)]
enum Prefix {
    Rooms,
    Backends,
    Receipts,
    ByRoom,
}

#[near(serializers = [json, borsh])]
#[derive(Clone, Debug, PartialEq)]
pub struct DataRoom {
    pub id: String,
    pub owner: AccountId,
    pub root_hash: String,
    pub file_count: u32,
    pub created_at: U64,
}

#[near(serializers = [json, borsh])]
#[derive(Clone, Debug, PartialEq)]
pub struct Receipt {
    pub id: u64,
    pub dataroom_id: String,
    pub dataroom_root: String,
    pub question_hash: String,
    pub answer_hash: String,
    pub request_hash: String,
    pub response_hash: String,
    pub completion_sig: String,
    pub model_id: String,
    pub attestation_hash: String,
    pub nonce: String,
    /// The backend's claim that every attestation check passed. A verifier
    /// recomputes it from the public attestation report rather than trusting it.
    pub attestation_checked_offchain: bool,
    pub recorded_by: AccountId,
    pub created_at: U64,
}

#[near(contract_state)]
#[derive(PanicOnDefault)]
pub struct Contract {
    rooms: LookupMap<String, DataRoom>,
    backends: LookupMap<String, Vec<AccountId>>,
    receipts: Vector<Receipt>,
    by_room: LookupMap<String, Vec<u64>>,
}

#[near]
impl Contract {
    #[init]
    pub fn new() -> Self {
        Self {
            rooms: LookupMap::new(Prefix::Rooms),
            backends: LookupMap::new(Prefix::Backends),
            receipts: Vector::new(Prefix::Receipts),
            by_room: LookupMap::new(Prefix::ByRoom),
        }
    }

    /// Commit a data room's root hash. The caller becomes the owner. Immutable once set.
    #[payable]
    pub fn commit_dataroom(&mut self, id: String, root_hash: String, file_count: u32) -> DataRoom {
        let start = env::storage_usage();
        assert_room_id(&id);
        assert_hex(&root_hash, 32, "root_hash");
        require!(file_count > 0, "file_count must be positive");
        require!(!self.rooms.contains_key(&id), "data room already committed");

        let room = DataRoom {
            id: id.clone(),
            owner: env::predecessor_account_id(),
            root_hash,
            file_count,
            created_at: U64(env::block_timestamp()),
        };
        self.rooms.insert(id.clone(), room.clone());
        self.rooms.flush();
        emit("dataroom_committed", json!({ "id": id, "root_hash": room.root_hash, "owner": room.owner, "file_count": file_count }));
        charge_storage(start);
        room
    }

    /// Owner only: allow a backend account to record receipts for this room.
    #[payable]
    pub fn set_backend(&mut self, dataroom_id: String, account: AccountId) {
        let start = env::storage_usage();
        let room = self.room_or_panic(&dataroom_id);
        require!(env::predecessor_account_id() == room.owner, "only the data room owner can set a backend");
        let mut list = self.backends.get(&dataroom_id).cloned().unwrap_or_default();
        if !list.contains(&account) {
            require!(list.len() < MAX_BACKENDS, "too many backends");
            list.push(account.clone());
        }
        self.backends.insert(dataroom_id.clone(), list);
        self.backends.flush();
        emit("backend_set", json!({ "dataroom_id": dataroom_id, "account": account }));
        charge_storage(start);
    }

    /// Record one answer receipt. Panics unless the caller is the owner or an
    /// allow-listed backend, and unless `dataroom_root` equals the committed root.
    #[allow(clippy::too_many_arguments)]
    #[payable]
    pub fn record_receipt(
        &mut self,
        dataroom_id: String,
        dataroom_root: String,
        question_hash: String,
        answer_hash: String,
        request_hash: String,
        response_hash: String,
        completion_sig: String,
        model_id: String,
        attestation_hash: String,
        nonce: String,
        attestation_checked_offchain: bool,
    ) -> u64 {
        let start = env::storage_usage();
        let room = self.room_or_panic(&dataroom_id);
        let caller = env::predecessor_account_id();
        let allowed = caller == room.owner
            || self.backends.get(&dataroom_id).is_some_and(|l| l.contains(&caller));
        require!(allowed, "caller is not the data room owner or an allow-listed backend");
        require!(dataroom_root == room.root_hash, "dataroom_root does not match the committed root");

        for (value, name) in [
            (&question_hash, "question_hash"),
            (&answer_hash, "answer_hash"),
            (&request_hash, "request_hash"),
            (&response_hash, "response_hash"),
            (&attestation_hash, "attestation_hash"),
            (&nonce, "nonce"),
        ] {
            assert_hex(value, 32, name);
        }
        assert_hex(completion_sig.strip_prefix("0x").unwrap_or(&completion_sig), 65, "completion_sig");
        require!(!model_id.is_empty() && model_id.len() <= MAX_MODEL_LEN, "bad model_id");

        let id = self.receipts.len() as u64;
        let receipt = Receipt {
            id,
            dataroom_id: dataroom_id.clone(),
            dataroom_root,
            question_hash,
            answer_hash,
            request_hash,
            response_hash,
            completion_sig,
            model_id,
            attestation_hash,
            nonce,
            attestation_checked_offchain,
            recorded_by: caller,
            created_at: U64(env::block_timestamp()),
        };
        emit(
            "receipt_recorded",
            json!({
                "id": id,
                "dataroom_id": dataroom_id,
                "answer_hash": receipt.answer_hash,
                "attestation_checked_offchain": attestation_checked_offchain,
            }),
        );
        self.receipts.push(receipt);
        let mut ids = self.by_room.get(&dataroom_id).cloned().unwrap_or_default();
        ids.push(id);
        self.by_room.insert(dataroom_id, ids);
        self.receipts.flush();
        self.by_room.flush();
        charge_storage(start);
        id
    }

    pub fn get_dataroom(&self, id: String) -> Option<DataRoom> {
        self.rooms.get(&id).cloned()
    }

    pub fn get_backends(&self, dataroom_id: String) -> Vec<AccountId> {
        self.backends.get(&dataroom_id).cloned().unwrap_or_default()
    }

    pub fn get_receipt(&self, id: u64) -> Option<Receipt> {
        u32::try_from(id).ok().and_then(|i| self.receipts.get(i)).cloned()
    }

    /// Receipts for a room, oldest first. `limit` is capped at 50.
    pub fn get_receipts(&self, dataroom_id: String, from_index: Option<u64>, limit: Option<u64>) -> Vec<Receipt> {
        let Some(ids) = self.by_room.get(&dataroom_id) else {
            return vec![];
        };
        let from = from_index.unwrap_or(0) as usize;
        let limit = limit.unwrap_or(MAX_PAGE).min(MAX_PAGE) as usize;
        ids.iter()
            .skip(from)
            .take(limit)
            .filter_map(|&i| self.receipts.get(i as u32).cloned())
            .collect()
    }

    pub fn receipt_count(&self) -> u64 {
        self.receipts.len() as u64
    }

    fn room_or_panic(&self, id: &String) -> DataRoom {
        self.rooms.get(id).cloned().unwrap_or_else(|| env::panic_str("unknown data room"))
    }
}

fn assert_room_id(id: &str) {
    require!(!id.is_empty() && id.len() <= MAX_ID_LEN, "data room id must be 1-64 chars");
    require!(
        id.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-' || b == b'_'),
        "data room id may only use a-z, 0-9, - and _"
    );
}

fn assert_hex(value: &str, bytes: usize, name: &str) {
    let ok = value.len() == bytes * 2 && value.bytes().all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase());
    if !ok {
        env::panic_str(&format!("{name} must be {bytes} bytes of lowercase hex"));
    }
}

fn emit(event: &str, data: near_sdk::serde_json::Value) {
    env::log_str(&format!(
        "EVENT_JSON:{}",
        json!({ "standard": "oathbox", "version": "1.0.0", "event": event, "data": [data] })
    ));
}

/// Keep exactly the storage cost of what this call added; refund the rest.
fn charge_storage(start: u64) {
    let added = env::storage_usage().saturating_sub(start);
    let cost = env::storage_byte_cost().saturating_mul(added as u128);
    let attached = env::attached_deposit();
    if attached < cost {
        env::panic_str(&format!(
            "attach at least {} yoctoNEAR to cover {added} bytes of storage",
            cost.as_yoctonear()
        ));
    }
    let refund = attached.saturating_sub(cost);
    if refund > NearToken::from_yoctonear(0) {
        Promise::new(env::predecessor_account_id()).transfer(refund).detach();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use near_sdk::test_utils::{accounts, VMContextBuilder};
    use near_sdk::testing_env;

    const ROOT: &str = "623aca2488b99be35930afe83d1347c491af4fef24cd4acfc1c4b785698f254c";
    const H: &str = "1111111111111111111111111111111111111111111111111111111111111111";

    fn sig() -> String {
        format!("0x{}", "ab".repeat(65))
    }

    fn ctx(caller: AccountId, deposit_near: u128) {
        let mut b = VMContextBuilder::new();
        b.predecessor_account_id(caller.clone())
            .signer_account_id(caller)
            .attached_deposit(NearToken::from_millinear(deposit_near * 1000));
        testing_env!(b.build());
    }

    fn setup() -> Contract {
        ctx(accounts(0), 1);
        let mut c = Contract::new();
        c.commit_dataroom("acme-demo".into(), ROOT.into(), 13);
        c
    }

    fn record(c: &mut Contract, root: &str) -> u64 {
        c.record_receipt(
            "acme-demo".into(),
            root.into(),
            H.into(),
            H.into(),
            H.into(),
            H.into(),
            sig(),
            "Qwen/Qwen3.6-35B-A3B-FP8".into(),
            H.into(),
            H.into(),
            true,
        )
    }

    #[test]
    fn commit_and_read_back() {
        let c = setup();
        let room = c.get_dataroom("acme-demo".into()).unwrap();
        assert_eq!(room.root_hash, ROOT);
        assert_eq!(room.owner, accounts(0));
        assert_eq!(room.file_count, 13);
    }

    #[test]
    #[should_panic(expected = "data room already committed")]
    fn commit_is_immutable() {
        let mut c = setup();
        c.commit_dataroom("acme-demo".into(), H.into(), 1);
    }

    #[test]
    #[should_panic(expected = "root_hash must be 32 bytes of lowercase hex")]
    fn commit_rejects_bad_hash() {
        ctx(accounts(0), 1);
        let mut c = Contract::new();
        c.commit_dataroom("x".into(), "not-a-hash".into(), 1);
    }

    #[test]
    fn owner_can_record_and_list() {
        let mut c = setup();
        assert_eq!(record(&mut c, ROOT), 0);
        assert_eq!(record(&mut c, ROOT), 1);
        let all = c.get_receipts("acme-demo".into(), None, None);
        assert_eq!(all.len(), 2);
        assert_eq!(all[1].id, 1);
        assert_eq!(c.get_receipts("acme-demo".into(), Some(1), Some(10)).len(), 1);
        assert_eq!(c.get_receipt(0).unwrap().recorded_by, accounts(0));
        assert!(c.get_receipt(9).is_none());
    }

    #[test]
    #[should_panic(expected = "dataroom_root does not match the committed root")]
    fn wrong_root_rejected() {
        let mut c = setup();
        record(&mut c, H);
    }

    #[test]
    #[should_panic(expected = "caller is not the data room owner or an allow-listed backend")]
    fn stranger_cannot_record() {
        let mut c = setup();
        ctx(accounts(1), 1);
        record(&mut c, ROOT);
    }

    #[test]
    fn allow_listed_backend_can_record() {
        let mut c = setup();
        c.set_backend("acme-demo".into(), accounts(2));
        assert_eq!(c.get_backends("acme-demo".into()), vec![accounts(2)]);
        ctx(accounts(2), 1);
        let id = record(&mut c, ROOT);
        assert_eq!(c.get_receipt(id).unwrap().recorded_by, accounts(2));
    }

    #[test]
    #[should_panic(expected = "only the data room owner can set a backend")]
    fn only_owner_sets_backend() {
        let mut c = setup();
        ctx(accounts(1), 1);
        c.set_backend("acme-demo".into(), accounts(1));
    }

    #[test]
    #[should_panic(expected = "attach at least")]
    fn storage_must_be_paid() {
        let mut c = setup();
        ctx(accounts(0), 0);
        record(&mut c, ROOT);
    }

    #[test]
    #[should_panic(expected = "completion_sig must be 65 bytes")]
    fn bad_signature_rejected() {
        let mut c = setup();
        c.record_receipt(
            "acme-demo".into(),
            ROOT.into(),
            H.into(),
            H.into(),
            H.into(),
            H.into(),
            "0x1234".into(),
            "m".into(),
            H.into(),
            H.into(),
            false,
        );
    }
}
