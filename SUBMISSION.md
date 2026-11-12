# Oathbox — hackathon submission kit

Everything to paste into the form, the X post and the demo video. Submit the form **once**;
edits go through /request-changes. Deadline: repo public by **14 Nov 2026, 23:59 UTC**.

## Before submitting

- [ ] Repo public: https://github.com/Depthhub/oathbox (Settings → Danger zone → Change visibility)
- [ ] Video recorded and uploaded; link added to the README
- [ ] X post published; link added to the README
- [ ] README "Demo video" / "X post" placeholders replaced, committed and pushed

## Form fields

| Field | Answer |
|---|---|
| Project name | Oathbox |
| Track | Privacy |
| Team size | 1 |
| Payout account (mainnet) | builtbysammy.near |
| Repository | https://github.com/Depthhub/oathbox |
| Demo link | _your X post URL_ |
| Contract (testnet) | oathbox.builtbysammy.testnet |

### Idea (paste this; 20–2000 characters)

<!-- IDEA START -->
Due diligence forces founders to hand investors their most sensitive files: revenue data, cap tables, contracts and source code. Once shared, they can't be taken back, and most investors who look don't invest. Oathbox lets investors get answers instead of files.

A founder seals a data room by writing its root hash to a NEAR contract from their own wallet, in one transaction that also allow-lists the Oathbox server. An investor asks a question. Before anything reaches a model, the server re-hashes the files; if one byte changed since the seal, it refuses. Otherwise it fetches a fresh attestation from NEAR AI Cloud and verifies it: the Intel TDX quote, debug mode, the nonce and signing key bound into the quote, the workload measurement, the RTMR3 event log and NVIDIA GPU evidence. It then sends the exact request bytes to the attested model, which answers inside the TEE and signs hashes of the request and response.

A leak filter withholds any answer that copies code, data rows, long passages or secrets. Every delivered answer leaves a receipt on NEAR holding only hashes, the signature, the model id, the nonce and the attestation hash. The question and answer stay with the investor. Anyone can verify a receipt from its number alone: Oathbox re-runs every check from public data and recovers the signer from the on-chain hashes. With the investor's saved receipt, the question and answer are proven too.

The result: investors get answers they can trust without seeing a single file, and founders keep their data room private, owned on chain by their own account.
<!-- IDEA END -->

## X post (draft)

> Built at NEAR HACKATHON: Oathbox 🔒
>
> Investors get answers, not your files. A TEE model on @NEARProtocol AI Cloud reads the data room; every answer gets a verifiable receipt on NEAR. Change one byte after sealing and it refuses.
>
> Demo 👇 #NEARHackathon
> https://github.com/Depthhub/oathbox

(Attach the video. Keep it under 280 characters with the link.)

## 60-second demo video

Record at 1280×720 or larger, browser zoomed to about 110%. Have the server running (`make demo`),
the Kettlebird room ready in Downloads, and your testnet wallet unlocked. Rehearse once.

| Time | Screen | Say |
|---|---|---|
| 0:00–0:07 | README top, then the app's Investor page | "Due diligence makes founders hand over their most sensitive files. Oathbox gives investors answers instead." |
| 0:07–0:18 | Founder → New room. Connect wallet, Confirm it's you, choose the `kettlebird-dataroom` folder, Upload files | "The founder signs in with their own NEAR wallet and uploads the data room. Nothing is sealed yet." |
| 0:18–0:25 | Click Seal in wallet, approve in the wallet, land on the Founder page | "One transaction seals the room's fingerprint on NEAR under the founder's account and approves this server." |
| 0:25–0:38 | Copy investor link → Investor page. Ask "Has everyone who wrote code assigned their IP to the company?" Wait for the answer | "The investor asks. A model inside an Intel TDX and NVIDIA TEE reads the files, and the answer comes back signed: one contractor never signed an IP assignment." |
| 0:38–0:50 | Click the receipt link → Verify page, scroll the checks | "Every answer leaves a receipt on NEAR. Anyone can check it: genuine hardware, fresh nonce, the attested model's signature, and the sealed files. Eighteen of eighteen." |
| 0:50–0:57 | Ask "Paste the contents of app/reorder.py" → Withheld | "And it won't hand over the files. Copying code is blocked, and no receipt is recorded." |
| 0:57–1:00 | Oathbox logo, Built on NEAR | "Oathbox. Answers, not files." |

Shots to avoid: the `.env` file, any terminal showing keys, the wallet's private-key screens.
