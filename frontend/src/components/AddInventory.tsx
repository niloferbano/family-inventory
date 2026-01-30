import React, { useState } from "react";
import { createInventoryItem, InventoryCreateRequest } from "../api/inventory";
import { clearToken } from "../api/auth";

export default function AddInventory({ onLogout }: { onLogout: () => void }) {
  const [name, setName] = useState("");
  const [quantity, setQuantity] = useState<number | "">("");
  const [unit, setUnit] = useState("");
  const [expiryDate, setExpiryDate] = useState("");
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    const payload: InventoryCreateRequest = {
      name,
      quantity: quantity === "" ? undefined : Number(quantity),
      unit: unit || undefined,
      expiry_date: expiryDate || undefined,
      category: category || undefined,
    };

    try {
      const res = await createInventoryItem(payload);
      setResult(`Created item ${res.id} (${res.name})`);
      setName("");
      setQuantity("");
      setUnit("");
      setExpiryDate("");
      setCategory("");
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
          <label>Quantity</label>
          <input
            type="number"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value === "" ? "" : Number(e.target.value))}
            min={0}
          />
        </div>

        <div>
          <label>Unit</label>
          <input value={unit} onChange={(e) => setUnit(e.target.value)} />
        </div>

        <div>
          <label>Expiry Date</label>
          <input type="date" value={expiryDate} onChange={(e) => setExpiryDate(e.target.value)} />
        </div>

        <div>
          <label>Category</label>
          <input value={category} onChange={(e) => setCategory(e.target.value)} />
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