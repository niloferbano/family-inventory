import React, { useCallback, useEffect, useMemo, useState } from "react";
import { clearToken } from "../api/auth";
import { addHomeMember, createHome, HomeSummary, listHomes, UserType } from "../api/homes";
import {
  InventoryCategory,
  InventoryItem,
  deleteInventoryItem,
  listInventoryItems,
  updateInventoryItem,
} from "../api/inventory";
import AddInventory from "./AddInventory";

const isUnauthorized = (err: unknown) => {
  const message = String(err ?? "");
  return message.includes("401") || message.toLowerCase().includes("unauthorized");
};

const CATEGORY_OPTIONS: Array<{ value: InventoryCategory; label: string }> = [
  { value: "kitchen", label: "Kitchen" },
  { value: "bathroom", label: "Bathroom" },
  { value: "cleaning", label: "Cleaning" },
  { value: "other", label: "Other" },
];

const MEMBER_ROLE_OPTIONS: Array<{ value: UserType; label: string }> = [
  { value: "residence", label: "Resident" },
  { value: "guest", label: "Guest" },
];

export default function InventoryHome({ onLogout }: { onLogout: () => void }) {
  const [homes, setHomes] = useState<HomeSummary[]>([]);
  const [homeId, setHomeId] = useState("");
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [loadingHomes, setLoadingHomes] = useState(true);
  const [loadingItems, setLoadingItems] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingItemId, setEditingItemId] = useState<string | null>(null);
  const [editValues, setEditValues] = useState({
    name: "",
    category: "kitchen" as InventoryCategory,
    quantity: 1,
    unit: "pcs",
    expiryDate: "",
    notes: "",
  });
  const [savingItemId, setSavingItemId] = useState<string | null>(null);
  const [deletingItemId, setDeletingItemId] = useState<string | null>(null);
  const [newHomeName, setNewHomeName] = useState("");
  const [creatingHome, setCreatingHome] = useState(false);
  const [homeFormError, setHomeFormError] = useState<string | null>(null);
  const [homeFormSuccess, setHomeFormSuccess] = useState<string | null>(null);
  const [showCreateHomeForm, setShowCreateHomeForm] = useState(false);
  const [showAddMemberForm, setShowAddMemberForm] = useState(false);
  const [memberForm, setMemberForm] = useState({
    homeId: "",
    email: "",
    role: "residence" as UserType,
  });
  const [addingMember, setAddingMember] = useState(false);
  const [memberFormError, setMemberFormError] = useState<string | null>(null);
  const [memberFormSuccess, setMemberFormSuccess] = useState<string | null>(null);

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
        setEditingItemId(null);
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

  useEffect(() => {
    if (homeId && !memberForm.homeId) {
      setMemberForm((prev) => ({ ...prev, homeId }));
    }
  }, [homeId, memberForm.homeId]);

  const selectedHome = useMemo(
    () => homes.find((home) => home.home_id === homeId),
    [homes, homeId]
  );

  const startEdit = (item: InventoryItem) => {
    setEditingItemId(item.id);
    setEditValues({
      name: item.name,
      category: item.category,
      quantity: item.quantity,
      unit: item.unit,
      expiryDate: item.expiry_date ?? "",
      notes: item.notes ?? "",
    });
  };

  const cancelEdit = () => {
    setEditingItemId(null);
  };

  const saveEdit = async () => {
    if (!editingItemId || !homeId) {
      return;
    }
    const trimmedName = editValues.name.trim();
    if (!trimmedName) {
      setError("Name is required.");
      return;
    }
    setSavingItemId(editingItemId);
    setError(null);
    try {
      const updated = await updateInventoryItem(homeId, editingItemId, {
        name: trimmedName,
        category: editValues.category,
        quantity: editValues.quantity,
        unit: editValues.unit,
        expiry_date: editValues.expiryDate ? editValues.expiryDate : null,
        notes: editValues.notes.trim() ? editValues.notes : null,
      });
      setItems((prev) =>
        prev.map((item) => (item.id === updated.id ? updated : item))
      );
      setEditingItemId(null);
    } catch (err) {
      if (isUnauthorized(err)) {
        handleLogout();
        return;
      }
      setError((err as Error)?.message ?? "Failed to update item.");
    } finally {
      setSavingItemId(null);
    }
  };

  const handleDelete = async (item: InventoryItem) => {
    if (!homeId) {
      return;
    }
    if (!window.confirm(`Delete "${item.name}"?`)) {
      return;
    }
    setDeletingItemId(item.id);
    setError(null);
    try {
      await deleteInventoryItem(homeId, item.id);
      setItems((prev) => prev.filter((row) => row.id !== item.id));
      if (editingItemId === item.id) {
        setEditingItemId(null);
      }
    } catch (err) {
      if (isUnauthorized(err)) {
        handleLogout();
        return;
      }
      setError((err as Error)?.message ?? "Failed to delete item.");
    } finally {
      setDeletingItemId(null);
    }
  };

  const submitNewHome = async (event: React.FormEvent) => {
    event.preventDefault();
    setHomeFormError(null);
    setHomeFormSuccess(null);
    const trimmedName = newHomeName.trim();
    if (!trimmedName) {
      setHomeFormError("Home name is required.");
      return;
    }
    setCreatingHome(true);
    try {
      const created = await createHome({ name: trimmedName });
      setNewHomeName("");
      setHomeFormSuccess(`Created home "${created.name}".`);
      setHomeId(created.id);
      await loadHomes();
      setShowCreateHomeForm(false);
    } catch (err) {
      if (isUnauthorized(err)) {
        handleLogout();
        return;
      }
      setHomeFormError((err as Error)?.message ?? "Failed to create home.");
    } finally {
      setCreatingHome(false);
    }
  };

  const submitAddMember = async (event: React.FormEvent) => {
    event.preventDefault();
    setMemberFormError(null);
    setMemberFormSuccess(null);
    if (!memberForm.homeId) {
      setMemberFormError("Select a home to add a member.");
      return;
    }
    const email = memberForm.email.trim();
    if (!email) {
      setMemberFormError("Member email is required.");
      return;
    }
    setAddingMember(true);
    try {
      const added = await addHomeMember(memberForm.homeId, {
        userEmail: email,
        userType: memberForm.role,
      });
      setMemberForm((prev) => ({
        ...prev,
        email: "",
        role: "residence",
      }));
      setMemberFormSuccess(`Added ${added.username} to ${added.home_name}.`);
      await loadHomes();
      setShowAddMemberForm(false);
    } catch (err) {
      if (isUnauthorized(err)) {
        handleLogout();
        return;
      }
      setMemberFormError((err as Error)?.message ?? "Failed to add member.");
    } finally {
      setAddingMember(false);
    }
  };

  return (
    <div style={{ maxWidth: 960, margin: "1rem auto", padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h3 style={{ margin: 0 }}>Inventory Home</h3>
          <p style={{ margin: "4px 0 0", color: "#555" }}>
            {selectedHome ? `Home: ${selectedHome.name}` : "Select a home to view inventory."}
          </p>
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <h4 style={{ margin: 0 }}>Your Homes</h4>
          <button
            type="button"
            onClick={() => {
              if (showCreateHomeForm) {
                setShowCreateHomeForm(false);
                return;
              }
              setHomeFormError(null);
              setHomeFormSuccess(null);
              setShowCreateHomeForm(true);
            }}
          >
            {showCreateHomeForm ? "Close Create Home" : "Create Home"}
          </button>
        </div>
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

      <div style={{ marginTop: 16 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <h4 style={{ marginBottom: 8 }}>Manage Homes</h4>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={() => {
                if (showAddMemberForm) {
                  setShowAddMemberForm(false);
                  return;
                }
                setMemberFormError(null);
                setMemberFormSuccess(null);
                setShowAddMemberForm(true);
              }}
            >
              {showAddMemberForm ? "Close Add Member" : "Add Member"}
            </button>
          </div>
        </div>
        <div
          style={{
            display: "grid",
            gap: 16,
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          }}
        >
          {showCreateHomeForm && (
            <form
              onSubmit={submitNewHome}
              style={{
                border: "1px solid #eee",
                borderRadius: 12,
                padding: 12,
                background: "#fafafa",
                display: "grid",
                gap: 10,
              }}
            >
              <div style={{ fontWeight: 600 }}>Create a home</div>
              <label style={{ display: "grid", gap: 4 }}>
                Home name
                <input
                  value={newHomeName}
                  onChange={(e) => setNewHomeName(e.target.value)}
                  placeholder="e.g., Main House"
                />
              </label>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button type="submit" disabled={creatingHome}>
                  {creatingHome ? "Creating..." : "Create Home"}
                </button>
                <button type="button" onClick={() => setShowCreateHomeForm(false)} disabled={creatingHome}>
                  Cancel
                </button>
              </div>
              {homeFormSuccess && <div style={{ color: "green" }}>{homeFormSuccess}</div>}
              {homeFormError && <div style={{ color: "crimson" }}>{homeFormError}</div>}
            </form>
          )}

          {showAddMemberForm && (
            <form
              onSubmit={submitAddMember}
              style={{
                border: "1px solid #eee",
                borderRadius: 12,
                padding: 12,
                background: "#fafafa",
                display: "grid",
                gap: 10,
              }}
            >
              <div style={{ fontWeight: 600 }}>Add a member</div>
              <label style={{ display: "grid", gap: 4 }}>
                Home
                <select
                  value={memberForm.homeId}
                  onChange={(e) =>
                    setMemberForm((prev) => ({ ...prev, homeId: e.target.value }))
                  }
                  disabled={loadingHomes || homes.length === 0}
                >
                  <option value="">Select</option>
                  {homes.map((home) => (
                    <option key={home.home_id} value={home.home_id}>
                      {home.name}
                    </option>
                  ))}
                </select>
              </label>
              <label style={{ display: "grid", gap: 4 }}>
                Member email
                <input
                  type="email"
                  value={memberForm.email}
                  onChange={(e) => setMemberForm((prev) => ({ ...prev, email: e.target.value }))}
                  placeholder="member@example.com"
                />
              </label>
              <label style={{ display: "grid", gap: 4 }}>
                Role
                <select
                  value={memberForm.role}
                  onChange={(e) =>
                    setMemberForm((prev) => ({
                      ...prev,
                      role: e.target.value as UserType,
                    }))
                  }
                >
                  {MEMBER_ROLE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button type="submit" disabled={addingMember || !memberForm.homeId}>
                  {addingMember ? "Adding..." : "Add Member"}
                </button>
                <button type="button" onClick={() => setShowAddMemberForm(false)} disabled={addingMember}>
                  Cancel
                </button>
              </div>
              <div style={{ fontSize: 12, color: "#666" }}>
                Members must already have an account.
              </div>
              {memberFormSuccess && <div style={{ color: "green" }}>{memberFormSuccess}</div>}
              {memberFormError && <div style={{ color: "crimson" }}>{memberFormError}</div>}
            </form>
          )}
        </div>
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
        <button type="button" onClick={() => setShowAddForm((prev) => !prev)} disabled={!homeId}>
          {showAddForm ? "Close" : "Add New Item"}
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
            {items.map((item) => {
              const isEditing = editingItemId === item.id;
              return (
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
                <div style={{ flex: 1, minWidth: 220 }}>
                  {isEditing ? (
                    <div style={{ display: "grid", gap: 8 }}>
                      <label style={{ display: "grid", gap: 4 }}>
                        Name
                        <input
                          value={editValues.name}
                          onChange={(e) =>
                            setEditValues((prev) => ({ ...prev, name: e.target.value }))
                          }
                        />
                      </label>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
                        <label style={{ display: "grid", gap: 4 }}>
                          Category
                          <select
                            value={editValues.category}
                            onChange={(e) =>
                              setEditValues((prev) => ({
                                ...prev,
                                category: e.target.value as InventoryCategory,
                              }))
                            }
                          >
                            {CATEGORY_OPTIONS.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label style={{ display: "grid", gap: 4 }}>
                          Quantity
                          <input
                            type="number"
                            min={0}
                            value={editValues.quantity}
                            onChange={(e) =>
                              setEditValues((prev) => ({
                                ...prev,
                                quantity:
                                  e.target.value === "" ? 0 : Number(e.target.value),
                              }))
                            }
                          />
                        </label>
                        <label style={{ display: "grid", gap: 4 }}>
                          Unit
                          <input
                            value={editValues.unit}
                            onChange={(e) =>
                              setEditValues((prev) => ({ ...prev, unit: e.target.value }))
                            }
                          />
                        </label>
                      </div>
                      <label style={{ display: "grid", gap: 4 }}>
                        Expiry Date
                        <input
                          type="date"
                          value={editValues.expiryDate}
                          onChange={(e) =>
                            setEditValues((prev) => ({
                              ...prev,
                              expiryDate: e.target.value,
                            }))
                          }
                        />
                      </label>
                      <label style={{ display: "grid", gap: 4 }}>
                        Notes
                        <textarea
                          rows={2}
                          value={editValues.notes}
                          onChange={(e) =>
                            setEditValues((prev) => ({ ...prev, notes: e.target.value }))
                          }
                        />
                      </label>
                    </div>
                  ) : (
                    <div>
                      <strong>{item.name}</strong>
                      <div style={{ fontSize: 12, color: "#555", marginTop: 4 }}>
                        {item.category} - {item.quantity} {item.unit}
                        {item.expiry_date ? ` - exp ${item.expiry_date}` : ""}
                      </div>
                      {item.notes && (
                        <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
                          {item.notes}
                        </div>
                      )}
                    </div>
                  )}
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  {isEditing ? (
                    <>
                      <button
                        type="button"
                        onClick={saveEdit}
                        disabled={savingItemId === item.id}
                      >
                        {savingItemId === item.id ? "Saving..." : "Save"}
                      </button>
                      <button type="button" onClick={cancelEdit} disabled={savingItemId === item.id}>
                        Cancel
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={() => startEdit(item)}
                        disabled={Boolean(editingItemId) && editingItemId !== item.id}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(item)}
                        disabled={
                          deletingItemId === item.id ||
                          (Boolean(editingItemId) && editingItemId !== item.id)
                        }
                      >
                        {deletingItemId === item.id ? "Deleting..." : "Delete"}
                      </button>
                    </>
                  )}
                </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
