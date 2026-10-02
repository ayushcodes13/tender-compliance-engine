"use client";

import { useEffect, useState } from "react";
import { AlertCircle, Check, File, RefreshCw, Upload } from "lucide-react";

import { api, OemDocumentItem, OemUploadResponse } from "@/lib/api/client";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
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

  const reload = async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await api.fetchOemDocuments(projectId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load OEM documents");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const upload = async (file: File) => {
    if (disabled || uploading) return;
    setUploading(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await api.uploadOemDocument(projectId, file, {
        document_type: "datasheet",
        vendor_name: vendorName.trim() || undefined,
        product_name: productName.trim() || undefined,
      });
      setSuccess(result);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "OEM upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="doclist-section">
      <div className="section-title-row">
        <div>
          <h2>OEM / vendor sources</h2>
          <p>Evidence comes only from these separately versioned source documents.</p>
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

      <div className="detail-row" style={{ gap: 12, alignItems: "flex-end" }}>
        <label style={{ flex: 1 }}>
          <span className="detail-label">Vendor</span>
          <input
            value={vendorName}
            onChange={(e) => setVendorName(e.target.value)}
            placeholder="Optional vendor name"
            disabled={disabled || uploading}
          />
        </label>
        <label style={{ flex: 1 }}>
          <span className="detail-label">Product</span>
          <input
            value={productName}
            onChange={(e) => setProductName(e.target.value)}
            placeholder="Optional product / model"
            disabled={disabled || uploading}
          />
        </label>
        <label className="button button-secondary button-small" style={{ cursor: disabled ? "not-allowed" : "pointer" }}>
          <Upload size={13} aria-hidden="true" />
          {uploading ? "Uploading…" : "Upload OEM PDF"}
          <input
            type="file"
            accept="application/pdf"
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

      {success ? (
        <div className="upload-success-banner">
          <Check size={14} aria-hidden="true" />
          Uploaded {success.filename} as OEM source v{success.version_number}.
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
          <strong>No OEM/vendor documents yet.</strong>
          <p>Upload a datasheet, manual, certificate, test report, or proposal before reviewing evidence.</p>
        </div>
      ) : (
        <table className="doclist-table">
          <thead>
            <tr>
              <th>Source</th>
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
                <td>{[item.vendor_name, item.product_name].filter(Boolean).join(" · ") || "—"}</td>
                <td>v{item.version_number}</td>
                <td>{formatBytes(item.size_bytes)}</td>
                <td>{item.processing_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
