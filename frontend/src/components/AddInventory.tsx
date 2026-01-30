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
  onLogout,
}: {
  homeId: string;
  onCreated?: () => void;
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
      const res = await createInventoryItem(homeId, payload);
      const created = res[0];
      setResult(`Created item ${created?.name ?? name}`);
      setName("");
      setQuantity(1);
      setUnit("pcs");
      setExpiryDate("");
      setCategory("kitchen");
      setNotes("");
      onCreated?.();
    } catch (err: any) {
      if (String(err).includes("401") || String(err).toLowerCase().includes("unauthorized")) {
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
    <div style={{ maxWidth: 640, margin: "1rem auto", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
        <h3>Add Inventory Item</h3>
        <button onClick={() => { clearToken(); onLogout(); }}>Logout</button>
      </div>

      <form onSubmit={submit}>
        <div>
          <label>Name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </div>

        <div>
          <label>Expiry Date</label>
          <input type="date" value={expiryDate} onChange={(e) => setExpiryDate(e.target.value)} />
        </div>

        <div>
          <label>Category</label>
          <select value={category} onChange={(e) => setCategory(e.target.value as InventoryCategory)}>
            {CATEGORY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label>Quantity</label>
          <input
            type="number"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value === "" ? 0 : Number(e.target.value))}
            min={0}
          />
        </div>

        <div>
          <label>Unit</label>
          <input value={unit} onChange={(e) => setUnit(e.target.value)} />
        </div>

        <div>
          <label>Notes</label>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
        </div>

        <div style={{ marginTop: 12 }}>
          <button type="submit" disabled={loading}>{loading ? "Adding…" : "Add Item"}</button>
        </div>

        {result && <div style={{ color: "green", marginTop: 8 }}>{result}</div>}
        {error && <div style={{ color: "crimson", marginTop: 8 }}>{error}</div>}
      </form>
    </div>
  );
}
