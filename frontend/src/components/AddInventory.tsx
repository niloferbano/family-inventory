import React, { useState, useEffect } from "react";
import {
  createInventoryItem,
  Product, ProductCandidate, ProductDetails, lookupProduct, searchProducts, createProduct,
  HouseholdCategory,
  listInventoryCategories,
  InventoryCreateRequest,
} from "../api/inventory";
import { clearToken } from "../api/auth";

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
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [barcode, setBarcode] = useState("");
  const [lookupPending, setLookupPending] = useState(false);
  const [lookupMessage, setLookupMessage] = useState("");
  const [candidate, setCandidate] = useState<ProductCandidate | null>(null);
  const [reviewedDetails, setReviewedDetails] = useState<ProductDetails | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  useEffect(() => {
    let cancelled = false;
    setProducts([]);
    const timer = setTimeout(() => {
      if (name.trim()) searchProducts(name.trim()).then(data => {
        if (!cancelled) setProducts(data);
      }).catch(() => { if (!cancelled) setError("Product search failed. Please try again."); });
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [name]);
  const [quantity, setQuantity] = useState(1);
  const [unit, setUnit] = useState("pcs");
  const [expiryDate, setExpiryDate] = useState("");
  const [category, setCategory] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [categories, setCategories] = useState<HouseholdCategory[]>([]);
  const [categoriesLoading, setCategoriesLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    setCategories([]);
    setCategory("");
    setCategoriesLoading(true);
    listInventoryCategories(homeId).then((data) => {
      if (!cancelled) setCategories(data);
    }).catch(() => {
      if (!cancelled) setError("Unable to load categories. Reopen the form to retry.");
    }).finally(() => { if (!cancelled) setCategoriesLoading(false); });
    return () => { cancelled = true; };
  }, [homeId]);

  async function handleLookup() {
    if (lookupPending || loading || !barcode.trim()) return;
    setLookupPending(true);
    setLookupMessage("");
    setError(null);
    setSelectedProduct(null);
    setReviewedDetails(null);
    setCandidate(null);
    try {
      const result = await lookupProduct(barcode.trim());
      if (result.source === "local" && result.product) {
        setSelectedProduct(result.product);
        setName(result.product.name);
        setLookupMessage("Product found in the catalog.");
      } else if (result.source === "external" && result.candidate) {
        setCandidate(result.candidate);
        setLookupMessage("Review this match before using it.");
      } else {
        setLookupMessage(result.source === "provider_unavailable"
          ? "Product lookup is temporarily unavailable. Enter the product manually."
          : "No product found. Enter the product manually.");
      }
    } catch (err) {
      if (String(err).includes("401")) { clearToken(); onLogout(); }
      else setError(err instanceof Error ? err.message : "Lookup failed. Try again or enter the product manually.");
    } finally { setLookupPending(false); }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (loading || lookupPending || candidate || categoriesLoading || !name.trim() || !categories.some(c => c.id === category)) return;
    setLoading(true);
    setError(null);
    setResult(null);

    if (!homeId) {
      setError("Select a home before adding inventory items.");
      setLoading(false);
      return;
    }

    try {
    const product = selectedProduct ?? await createProduct({ ...reviewedDetails, name: name.trim(), barcode: barcode.trim() || undefined });
    setSelectedProduct(product);
    const payload: InventoryCreateRequest = {
      product_id: product.id,
      household_category_id: category,
      quantity,
      unit,
      expiry_date: expiryDate || undefined,
      notes: notes || undefined,
    };

      await createInventoryItem(homeId, payload);
      setResult(`Successfully added "${name}"!`);
      setName("");
      setSelectedProduct(null);
      setBarcode("");
      setReviewedDetails(null);
      setLookupMessage("");
      setQuantity(1);
      setUnit("pcs");
      setExpiryDate("");
      setCategory("");
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
            onChange={(e) => { setName(e.target.value); setSelectedProduct(null); }}
            maxLength={100}
            disabled={loading || lookupPending}
            required
            style={{
              width: "100%",
              padding: 8,
              borderRadius: 6,
              border: "1px solid #d1d5db",
            }}
          />
          {products.length > 0 && !selectedProduct && (
            <label>Choose an existing product
              <select value="" onChange={e => {
                const product = products.find(p => p.id === e.target.value);
                if (product) { setSelectedProduct(product); setName(product.name); setBarcode(product.barcode ?? ""); setCandidate(null); setReviewedDetails(null); setLookupMessage(""); }
              }} disabled={loading || lookupPending}>
                <option value="">Select a product</option>
                {products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </label>
          )}
          <p>{selectedProduct ? "Using the selected product." : "Adding this item will create a new product unless you select an existing one."}</p>
        </div>

        <div>
          <label htmlFor="inventory-barcode">Barcode (optional)</label>
          <input id="inventory-barcode" value={barcode} maxLength={64}
            disabled={loading || lookupPending}
            onChange={e => {
              setBarcode(e.target.value); setCandidate(null); setSelectedProduct(null);
              setReviewedDetails(null); setLookupMessage("");
            }} />
          <button type="button" onClick={handleLookup}
            disabled={loading || lookupPending || !barcode.trim()}>
            {lookupPending ? "Looking up…" : "Look up product"}
          </button>
          {lookupMessage && <p role="status">{lookupMessage}</p>}
          {candidate && (
            <section aria-label="Product match">
              <p><strong>{candidate.name}</strong></p>
              {candidate.brand && <p>Brand: {candidate.brand}</p>}
              {candidate.external_category && <p>Catalog category: {candidate.external_category}</p>}
              <p>Source: {candidate.source}</p>
              <button type="button" onClick={() => {
                setName(candidate.name.slice(0, 100)); setBarcode(candidate.barcode);
                setReviewedDetails({
                  brand: candidate.brand?.slice(0, 100),
                  external_category: candidate.external_category?.slice(0, 100),
                  image_url: candidate.image_url?.slice(0, 500), name: candidate.name.slice(0, 100),
                });
                setCandidate(null); setLookupMessage("Match selected. Review the name and add the item to save it.");
              }}>Use this product</button>
              <button type="button" onClick={() => { setCandidate(null); setLookupMessage("Enter the product manually."); }}>Enter manually</button>
            </section>
          )}
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
              required
              disabled={categoriesLoading || loading || !categories.length}
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              style={{
                width: "100%",
                padding: 8,
                borderRadius: 6,
                border: "1px solid #d1d5db",
                background: "white",
              }}
            >
              <option value="">{categoriesLoading ? "Loading categories…" : categories.length ? "Select a category" : "No categories available for this home"}</option>
              {categories.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.name}
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
            disabled={loading || lookupPending || !!candidate || categoriesLoading || !category}
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
