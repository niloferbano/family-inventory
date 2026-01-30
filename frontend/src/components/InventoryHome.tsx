import React, { useCallback, useEffect, useMemo, useState } from "react";
import { clearToken } from "../api/auth";
import { listHomes, HomeSummary } from "../api/homes";
import { InventoryItem, listInventoryItems } from "../api/inventory";
import AddInventory from "./AddInventory";

const isUnauthorized = (err: unknown) => {
  const message = String(err ?? "");
  return message.includes("401") || message.toLowerCase().includes("unauthorized");
};

export default function InventoryHome({ onLogout }: { onLogout: () => void }) {
  const [homes, setHomes] = useState<HomeSummary[]>([]);
  const [homeId, setHomeId] = useState("");
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [loadingHomes, setLoadingHomes] = useState(true);
  const [loadingItems, setLoadingItems] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);

  const handleLogout = useCallback(() => {
    clearToken();
    onLogout();
  }, [onLogout]);

  const loadHomes = useCallback(async () => {
    setLoadingHomes(true);
    setError(null);
    try {
      const homesList = await listHomes();
      setHomes(homesList);
      if (homesList.length > 0) {
        setHomeId((current) => current || homesList[0].home_id);
      }
    } catch (err) {
      if (isUnauthorized(err)) {
        handleLogout();
        return;
      }
      setError((err as Error)?.message ?? "Failed to load homes.");
    } finally {
      setLoadingHomes(false);
    }
  }, [handleLogout]);

  const loadItems = useCallback(
    async (selectedHomeId: string) => {
      setLoadingItems(true);
      setError(null);
      try {
        const response = await listInventoryItems(selectedHomeId);
        setItems(response.results);
      } catch (err) {
        if (isUnauthorized(err)) {
          handleLogout();
          return;
        }
        setError((err as Error)?.message ?? "Failed to load inventory items.");
      } finally {
        setLoadingItems(false);
      }
    },
    [handleLogout]
  );

  useEffect(() => {
    loadHomes();
  }, [loadHomes]);

  useEffect(() => {
    if (homeId) {
      loadItems(homeId);
    }
  }, [homeId, loadItems]);

  const selectedHome = useMemo(
    () => homes.find((home) => home.home_id === homeId),
    [homes, homeId]
  );

  return (
    <div style={{ maxWidth: 960, margin: "1rem auto", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h3 style={{ margin: 0 }}>Inventory Home</h3>
          <p style={{ margin: "4px 0 0", color: "#555" }}>
            {selectedHome ? `Home: ${selectedHome.name}` : "Select a home to view inventory."}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" onClick={() => setShowAddForm((prev) => !prev)}>
            {showAddForm ? "Close" : "Add New Item"}
          </button>
          <button type="button" onClick={handleLogout}>Logout</button>
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <h4 style={{ margin: 0 }}>Your Homes</h4>
        {loadingHomes ? (
          <div style={{ marginTop: 8 }}>Loading homes...</div>
        ) : homes.length === 0 ? (
          <div style={{ marginTop: 8, color: "#555" }}>No homes found for this account yet.</div>
        ) : (
          <div style={{ marginTop: 12, display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
            {homes.map((home) => {
              const isActive = home.home_id === homeId;
              const memberCount = home.members?.length ?? 0;
              return (
                <button
                  key={home.home_id}
                  type="button"
                  onClick={() => setHomeId(home.home_id)}
                  style={{
                    textAlign: "left",
                    borderRadius: 12,
                    padding: 12,
                    border: isActive ? "2px solid #1c1b1f" : "1px solid #e0e0e0",
                    background: "#fff",
                    cursor: "pointer",
                  }}
                >
                  <div style={{ fontWeight: 600 }}>{home.name}</div>
                  <div style={{ marginTop: 6, fontSize: 12, color: "#666" }}>
                    Members: {memberCount}
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div style={{ marginTop: 12, display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        <label>
          Home
          <select
            value={homeId}
            onChange={(e) => setHomeId(e.target.value)}
            disabled={loadingHomes || homes.length === 0}
            style={{ marginLeft: 8 }}
          >
            <option value="">Select</option>
            {homes.map((home) => (
              <option key={home.home_id} value={home.home_id}>
                {home.name}
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={() => homeId && loadItems(homeId)} disabled={!homeId || loadingItems}>
          Refresh
        </button>
      </div>

      {error && <div style={{ color: "crimson", marginTop: 12 }}>{error}</div>}

      {showAddForm && (
        <div style={{ marginTop: 16 }}>
          <AddInventory homeId={homeId} onCreated={() => homeId && loadItems(homeId)} onLogout={handleLogout} />
        </div>
      )}

      <div style={{ marginTop: 24 }}>
        <h4 style={{ marginBottom: 8 }}>Inventory Items</h4>
        {loadingItems ? (
          <div>Loading inventory...</div>
        ) : items.length === 0 ? (
          <div>No inventory items found.</div>
        ) : (
          <div style={{ display: "grid", gap: 12 }}>
            {items.map((item) => (
              <div
                key={item.id}
                style={{
                  border: "1px solid #eee",
                  borderRadius: 10,
                  padding: 12,
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 12,
                  flexWrap: "wrap",
                }}
              >
                <div>
                  <strong>{item.name}</strong>
                  <div style={{ fontSize: 12, color: "#555", marginTop: 4 }}>
                    {item.category} - {item.quantity} {item.unit}
                    {item.expiry_date ? ` - exp ${item.expiry_date}` : ""}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button type="button" disabled title="Update not available yet">
                    Update
                  </button>
                  <button type="button" disabled title="Delete not available yet">
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
