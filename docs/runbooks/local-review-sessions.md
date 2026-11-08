# Save and resume a local review session

The Phase 1 review workspace can save its extracted analysis, source references, review marks, and response-sheet edits to a portable `.tce-review` file. The file is encrypted in the browser; it is not uploaded to the app server or a cloud store.

## Save

1. In the tender review, select **Save review**.
2. Enter and confirm a long, unique passphrase. The application does not store or recover it.
3. Save the downloaded `.tce-review` file somewhere protected, separately from the original tender PDF.

## Resume

1. Select **Resume saved review** and choose the `.tce-review` file.
2. Enter the passphrase used when saving.
3. Select the exact original tender PDF. The browser computes SHA-256 locally and restores the review only if it matches the saved document fingerprint.

The source PDF is intentionally not copied into the session file. Keep the PDF and encrypted review file together. A changed or re-saved PDF will fail the fingerprint check, even if it looks visually identical. Exports remain available after a successful restore, but source-page viewing requires the matching original PDF.

## Security and limits

- Encryption uses Web Crypto PBKDF2-HMAC-SHA-256 with 600,000 iterations to derive an AES-256-GCM key, a random 16-byte salt, and a random 12-byte IV. The authenticated encryption covers the serialized review data.
- The bundle is limited to 90 MiB and the decrypted session to 64 MiB. A browser with Web Crypto in a secure context (HTTPS or localhost) is required.
- The passphrase is never stored. Losing it makes the encrypted review unrecoverable. Use a strong, unique passphrase and protect the bundle as sensitive tender data.
- This is a manual download/import workflow, not automatic autosave or multi-device synchronization. Browser memory still holds plaintext while the review is open. The original PDF is not encrypted by this feature.
- Portable sessions currently cover Phase 1 tender review only. The UI disables saving after OEM product-document/compliance state is added.
- Imported content is treated as untrusted and structurally bounded. The PDF fingerprint is checked before restoring citations; this does not certify the extraction or the tender's completeness.

The KDF parameters follow OWASP's current PBKDF2-HMAC-SHA-256 guidance. AES-GCM and Web Crypto parameters follow the [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html) and [MDN Web Crypto deriveKey reference](https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/deriveKey). Recheck those recommendations before changing the file format.
