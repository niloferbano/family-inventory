import React, { useState } from "react";
import {
  createInventoryItem,
  InventoryCategory,
  InventoryCreateRequest,
} from "../api/inventory";
import { clearToken } from "../api/auth";

const CATEGORY_OPTIONS: Array<{ value: InventoryCategory; label: string }> = [
  { value: "kitchen", label: "Kitchen" },
  { value: "bathroom", label: "Bathroom" },
  { value: "cleaning", label: "Cleaning" },
  { value: "other", label: "Other" },
];

export default function AddInventory({
  homeId,
  onCreated,
  onCancel,
  onLogout,
}: {
  homeId: string;
  onCreated?: () => void;
  onCancel: () => void;
  onLogout: () => void;
}) {
  const [name, setName] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [unit, setUnit] = useState("pcs");
  const [expiryDate, setExpiryDate] = useState("");
  const [category, setCategory] = useState<InventoryCategory>("kitchen");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    if (!homeId) {
      setError("Select a home before adding inventory items.");
      setLoading(false);
      return;
    }

    const payload: InventoryCreateRequest = {
      name,
      category,
      quantity,
      unit,
      expiry_date: expiryDate || undefined,
      notes: notes || undefined,
    };

    try {
      await createInventoryItem(homeId, payload);
      setResult(`Successfully added "${name}"!`);
      setName("");
      setQuantity(1);
      setUnit("pcs");
      setExpiryDate("");
      setCategory("kitchen");
      setNotes("");

      onCreated?.();
      setTimeout(() => {
        onCancel(); // Automatically closes the popup after successful add
      }, 700);
    } catch (err: any) {
      if (
        String(err).includes("401") ||
        String(err).toLowerCase().includes("unauthorized")
      ) {
        clearToken();
        onLogout();
        return;
      }
      setError(err?.message ?? "Failed to create inventory item");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ padding: 20 }}>
      {/* Popup Header with Functional Close Button */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
          borderBottom: "1px solid #e5e7eb",
          paddingBottom: 10,
        }}
      >
        <h3 style={{ margin: 0, fontSize: "1.2rem", color: "#111827" }}>
          Add Inventory Item
        </h3>
        <button
          type="button"
          onClick={onCancel}
          style={{
            background: "transparent",
            border: "none",
            fontSize: "1.2rem",
            color: "#6b7280",
            cursor: "pointer",
            fontWeight: "bold",
            padding: "4px 8px",
          }}
        >
          ✕
        </button>
      </div>

      <form
        onSubmit={submit}
        style={{ display: "flex", flexDirection: "column", gap: 12 }}
      >
        <div>
          <label
            style={{
              display: "block",
              marginBottom: 4,
              fontSize: "0.9rem",
              fontWeight: 500,
            }}
          >
            Name *
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            style={{
              width: "100%",
              padding: 8,
              borderRadius: 6,
              border: "1px solid #d1d5db",
            }}
          />
        </div>

        <div
          style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}
        >
          <div>
            <label
              style={{
                display: "block",
                marginBottom: 4,
                fontSize: "0.9rem",
                fontWeight: 500,
              }}
            >
              Category
            </label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value as InventoryCategory)}
              style={{
                width: "100%",
                padding: 8,
                borderRadius: 6,
                border: "1px solid #d1d5db",
                background: "white",
              }}
            >
              {CATEGORY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              style={{
                display: "block",
                marginBottom: 4,
                fontSize: "0.9rem",
                fontWeight: 500,
              }}
            >
              Expiry Date
            </label>
            <input
              type="date"
              value={expiryDate}
              onChange={(e) => setExpiryDate(e.target.value)}
              style={{
                width: "100%",
                padding: 8,
                borderRadius: 6,
                border: "1px solid #d1d5db",
                background: "white",
              }}
            />
          </div>
        </div>

        <div
          style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}
        >
          <div>
            <label
              style={{
                display: "block",
                marginBottom: 4,
                fontSize: "0.9rem",
                fontWeight: 500,
              }}
            >
              Quantity
            </label>
            <input
              type="number"
              value={quantity}
              onChange={(e) =>
                setQuantity(e.target.value === "" ? 0 : Number(e.target.value))
              }
              min={0}
              style={{
                width: "100%",
                padding: 8,
                borderRadius: 6,
                border: "1px solid #d1d5db",
              }}
            />
          </div>

          <div>
            <label
              style={{
                display: "block",
                marginBottom: 4,
                fontSize: "0.9rem",
                fontWeight: 500,
              }}
            >
              Unit
            </label>
            <input
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
              style={{
                width: "100%",
                padding: 8,
                borderRadius: 6,
                border: "1px solid #d1d5db",
              }}
            />
          </div>
        </div>

        <div>
          <label
            style={{
              display: "block",
              marginBottom: 4,
              fontSize: "0.9rem",
              fontWeight: 500,
            }}
          >
            Notes
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            style={{
              width: "100%",
              padding: 8,
              borderRadius: 6,
              border: "1px solid #d1d5db",
            }}
          />
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button
            type="submit"
            disabled={loading}
            style={{
              flex: 2,
              background: "#2563eb",
              color: "white",
              border: "none",
              padding: "10px",
              borderRadius: 6,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {loading ? "Adding…" : "Add Item"}
          </button>

          {/* Functional Cancel Button */}
          <button
            type="button"
            onClick={onCancel}
            style={{
              flex: 1,
              background: "#e5e7eb",
              color: "#374151",
              border: "none",
              padding: "10px",
              borderRadius: 6,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Cancel
          </button>
        </div>

        {result && (
          <div
            style={{
              color: "#059669",
              background: "#ecfdf5",
              padding: 8,
              borderRadius: 6,
              textAlign: "center",
              fontSize: "0.9rem",
            }}
          >
            {result}
          </div>
        )}
        {error && (
          <div
            style={{
              color: "#dc2626",
              background: "#fef2f2",
              padding: 8,
              borderRadius: 6,
              textAlign: "center",
              fontSize: "0.9rem",
            }}
          >
            {error}
          </div>
        )}
      </form>
    </div>
  );
}
