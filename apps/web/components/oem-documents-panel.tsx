"use client";

import { useEffect, useState } from "react";
import { AlertCircle, Check, File, RefreshCw, Upload } from "lucide-react";

import { api, OemDocumentItem, OemUploadResponse } from "@/lib/api/client";

const DOCUMENT_TYPES = [
  ["datasheet", "Datasheet"],
  ["brochure", "Brochure"],
  ["manual", "Manual"],
  ["certificate", "Certificate"],
  ["test_report", "Test report"],
  ["quotation", "Quotation"],
  ["proposal", "Proposal"],
  ["compliance_sheet", "Vendor compliance sheet"],
  ["other", "Other"],
] as const;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

function statusLabel(status: string): string {
  return status.replaceAll("_", " ").replace(/^./, (value) => value.toUpperCase());
}

export function OemDocumentsPanel(props: {
  projectId: string;
  disabled?: boolean;
}) {
  const { projectId, disabled = false } = props;
  const [items, setItems] = useState<OemDocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<OemUploadResponse | null>(null);
  const [vendorName, setVendorName] = useState("");
  const [productName, setProductName] = useState("");
  const [documentType, setDocumentType] = useState("datasheet");

  const reload = async (showLoading = true) => {
    if (showLoading) setLoading(true);
    setError(null);
    try {
      setItems(await api.fetchOemDocuments(projectId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load OEM documents");
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const hasProcessingItems = items.some((item) =>
    ["uploaded", "queued", "processing"].includes(item.processing_status)
  );

  useEffect(() => {
    if (!hasProcessingItems) return;
    const timer = window.setInterval(() => void reload(false), 2500);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasProcessingItems, projectId]);

  const upload = async (file: File) => {
    if (disabled || uploading) return;
    setUploading(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await api.uploadOemDocument(projectId, file, {
        document_type: documentType,
        vendor_name: vendorName.trim() || undefined,
        product_name: productName.trim() || undefined,
      });
      setSuccess(result);
      await reload(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "OEM upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="doclist-section source-section-anchor" id="vendor-sources">
      <div className="section-title-row">
        <div>
          <p className="eyebrow">Step 2 · Vendor / OEM</p>
          <h2>Vendor / OEM sources</h2>
          <p>
            Upload datasheets, manuals, test reports, certificates, proposals,
            quotations, or an existing vendor compliance sheet. These sources
            support the response; the product does not assume their claims are true
            until they are reviewed against the tender.
          </p>
        </div>
        <button
          className="button button-secondary button-small"
          type="button"
          onClick={() => void reload()}
          disabled={loading}
        >
          <RefreshCw size={12} aria-hidden="true" />
          Refresh
        </button>
      </div>

      <div className="oem-upload-grid">
        <label>
          <span className="detail-label">Document type</span>
          <select
            value={documentType}
            onChange={(event) => setDocumentType(event.target.value)}
            disabled={disabled || uploading}
          >
            {DOCUMENT_TYPES.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label>
          <span className="detail-label">Vendor</span>
          <input
            value={vendorName}
            onChange={(e) => setVendorName(e.target.value)}
            placeholder="e.g. Acme Instruments"
            disabled={disabled || uploading}
          />
        </label>
        <label>
          <span className="detail-label">Product / model</span>
          <input
            value={productName}
            onChange={(e) => setProductName(e.target.value)}
            placeholder="e.g. Model X"
            disabled={disabled || uploading}
          />
        </label>
        <label
          className="button button-secondary button-small oem-upload-button"
          style={{ cursor: disabled ? "not-allowed" : "pointer" }}
        >
          <Upload size={13} aria-hidden="true" />
          {uploading
            ? "Uploading…"
            : documentType === "compliance_sheet"
              ? "Upload compliance sheet"
              : "Upload source"}
          <input
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            style={{ display: "none" }}
            disabled={disabled || uploading}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void upload(file);
              e.target.value = "";
            }}
          />
        </label>
      </div>
      <p className="field-help">PDF or DOCX · datasheets, manuals, certificates, test reports, proposals, quotations, or vendor compliance sheets.</p>

      {success ? (
        <div className="upload-success-banner">
          <Check size={14} aria-hidden="true" />
          Uploaded {success.filename} as OEM source v{success.version_number}. Processing will update automatically.
        </div>
      ) : null}
      {error ? (
        <div className="upload-error-banner" role="alert">
          <AlertCircle size={14} aria-hidden="true" />
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="empty-state"><strong>Loading OEM sources…</strong></div>
      ) : items.length === 0 ? (
        <div className="empty-state">
          <File size={22} aria-hidden="true" />
          <strong>No vendor/OEM sources yet.</strong>
          <p>
            Add at least one technical source or an existing vendor compliance
            sheet before you review compliance.
          </p>
        </div>
      ) : (
        <table className="doclist-table">
          <thead>
            <tr>
              <th>Source</th>
              <th>Type</th>
              <th>Vendor / product</th>
              <th>Version</th>
              <th>Size</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={`${item.document_id}-${item.version_number}`}>
                <td><File size={13} aria-hidden="true" /> {item.display_name}</td>
                <td>{statusLabel(item.document_type)}</td>
                <td>{[item.vendor_name, item.product_name].filter(Boolean).join(" · ") || "—"}</td>
                <td>v{item.version_number}</td>
                <td>{formatBytes(item.size_bytes)}</td>
                <td><span className="status-pill status-neutral">{statusLabel(item.processing_status)}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
