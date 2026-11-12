// Must be imported before anything from @near-wallet-selector: MyNearWallet uses Node's Buffer.
import { Buffer } from "buffer";

if (!globalThis.Buffer) globalThis.Buffer = Buffer;
