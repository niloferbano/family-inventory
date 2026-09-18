import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { clearToken } from "../api/auth";
import {
  addHomeMember,
  createHome,
  HomeSummary,
  listHomes,
  UserType,
} from "../api/homes";
import {
  HouseholdCategory,
  listInventoryCategories,
  InventoryItem,
  deleteInventoryItem,
  listInventoryItems,
  updateInventoryItem,
} from "../api/inventory";
import AddInventory from "./AddInventory";
import NotificationBell from "./NotificationBell";
import { useSearchParams } from "react-router-dom";

const isUnauthorized = (err: unknown) => {
  const message = String(err ?? "");
  return (
    message.includes("401") || message.toLowerCase().includes("unauthorized")
  );
};

const MEMBER_ROLE_OPTIONS: Array<{ value: UserType; label: string }> = [
  { value: "residence", label: "Resident" },
  { value: "guest", label: "Guest" },
];

export default function InventoryHome({ onLogout }: { onLogout: () => void }) {
  const [homes, setHomes] = useState<HomeSummary[]>([]);
  const [homeId, setHomeId] = useState("");
  const [categories, setCategories] = useState<HouseholdCategory[]>([]);
  useEffect(() => {
    let cancelled = false;
    setCategories([]);
    if (homeId) listInventoryCategories(homeId).then(data => {
      if (!cancelled) setCategories(data);
    }).catch(() => { if (!cancelled) setError("Unable to load categories."); });
    return () => { cancelled = true; };
  }, [homeId]);
  const categoryName = (id: string) => categories.find(c => c.id === id)?.name ?? "Category unavailable";
  const CATEGORY_OPTIONS = categories.map(c => ({ value: c.id, label: c.name }));
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [loadingHomes, setLoadingHomes] = useState(true);
  const [loadingItems, setLoadingItems] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [searchParams] = useSearchParams();
  const urlHomeId = searchParams.get("home");
  const highlightItemName = searchParams.get("highlight")?.toLowerCase() || "";

  // Reference map for auto-scrolling to highlighted items
  const itemRefs = useRef<{ [key: string]: HTMLDivElement | null }>({});

  // When homes load OR when the URL parameter changes, update active homeId
  useEffect(() => {
    if (urlHomeId && homes.some((h) => h.home_id === urlHomeId)) {
      setHomeId(urlHomeId);
    }
  }, [urlHomeId, homes]);

  // Modal States
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [showCreateHomeForm, setShowCreateHomeForm] = useState(false);
  const [showAddMemberForm, setShowAddMemberForm] = useState(false);

  // Sorting State
  const [sortBy, setSortBy] = useState<"default" | "category" | "expiry">(
    "default",
  );

  const [editingItemId, setEditingItemId] = useState<string | null>(null);
  const [editValues, setEditValues] = useState({
    name: "",
    household_category_id: "",
    quantity: 1,
    unit: "pcs",
    expiryDate: "",
    notes: "",
  });
  const [savingItemId, setSavingItemId] = useState<string | null>(null);
  const [deletingItemId, setDeletingItemId] = useState<string | null>(null);

  // Home & Member form states
  const [newHomeName, setNewHomeName] = useState("");
  const [creatingHome, setCreatingHome] = useState(false);
  const [homeFormError, setHomeFormError] = useState<string | null>(null);
  const [homeFormSuccess, setHomeFormSuccess] = useState<string | null>(null);

  const [memberForm, setMemberForm] = useState({
    homeId: "",
    email: "",
    role: "residence" as UserType,
  });
  const [addingMember, setAddingMember] = useState(false);
  const [memberFormError, setMemberFormError] = useState<string | null>(null);
  const [memberFormSuccess, setMemberFormSuccess] = useState<string | null>(
    null,
  );

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
      if (homesList.length > 0 && !homeId && !urlHomeId) {
        setHomeId(homesList[0].home_id);
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
  }, [handleLogout, homeId, urlHomeId]);

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
    [handleLogout],
  );

  useEffect(() => {
    void loadHomes();
  }, [loadHomes]);

  useEffect(() => {
    if (homeId) {
      void loadItems(homeId);
    }
  }, [homeId, loadItems]);

  useEffect(() => {
    if (homeId && !memberForm.homeId) {
      setMemberForm((prev) => ({ ...prev, homeId }));
    }
  }, [homeId, memberForm.homeId]);

  // Auto-scroll and highlight target item from URL search query
  useEffect(() => {
    if (highlightItemName && items.length > 0) {
      const matchedItem = items.find((i) =>
        i.name.toLowerCase().includes(highlightItemName),
      );
      if (matchedItem && itemRefs.current[matchedItem.id]) {
        itemRefs.current[matchedItem.id]?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      }
    }
  }, [highlightItemName, items]);

  const selectedHome = useMemo(
    () => homes.find((home) => home.home_id === homeId),
    [homes, homeId],
  );

  const startEdit = (item: InventoryItem) => {
    setEditingItemId(item.id);
    setEditValues({
      name: item.name,
      household_category_id: item.household_category_id,
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

        household_category_id: editValues.household_category_id,
        quantity: editValues.quantity,
        unit: editValues.unit,
        expiry_date: editValues.expiryDate ? editValues.expiryDate : null,
        notes: editValues.notes.trim() ? editValues.notes : null,
      });
      setItems((prev) =>
        prev.map((item) => (item.id === updated.id ? updated : item)),
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

  // Sorting Logic
  const sortedItems = [...items].sort((a, b) => {
    if (sortBy === "category") {
      return categoryName(a.household_category_id).localeCompare(categoryName(b.household_category_id));
    } else if (sortBy === "expiry") {
      if (!a.expiry_date) return 1;
      if (!b.expiry_date) return -1;
      return (
        new Date(a.expiry_date).getTime() - new Date(b.expiry_date).getTime()
      );
    }
    return 0;
  });

  return (
    <div style={{ maxWidth: 960, margin: "1rem auto", padding: 16 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 12,
        }}
      >
        <div>
          <h3 style={{ margin: 0 }}>Inventory Home</h3>
          <p style={{ margin: "4px 0 0", color: "#555" }}>
            {selectedHome
              ? `Home: ${selectedHome.name}`
              : "Select a home to view inventory."}
          </p>
        </div>
      </div>

      {/* Action Buttons Bar */}
      <div
        style={{ marginTop: 16, display: "flex", gap: 12, flexWrap: "wrap" }}
      >
        <button
          type="button"
          onClick={() => {
            setHomeFormError(null);
            setHomeFormSuccess(null);
            setShowCreateHomeForm(true);
          }}
          style={{
            background: "#4b5563",
            color: "white",
            border: "none",
            padding: "8px 16px",
            borderRadius: 6,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          + Create Home
        </button>
        <button
          type="button"
          onClick={() => {
            setMemberFormError(null);
            setMemberFormSuccess(null);
            setShowAddMemberForm(true);
          }}
          disabled={homes.length === 0}
          style={{
            background: "#10b981",
            color: "white",
            border: "none",
            padding: "8px 16px",
            borderRadius: 6,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          + Add Member
        </button>
      </div>

      {/* CREATE HOME POPUP MODAL */}
      {showCreateHomeForm && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            width: "100vw",
            height: "100vh",
            background: "rgba(0,0,0,0.5)",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            zIndex: 9999,
          }}
        >
          <div
            style={{
              background: "white",
              padding: 24,
              borderRadius: 12,
              width: "100%",
              maxWidth: 420,
              boxShadow: "0 10px 25px rgba(0,0,0,0.2)",
            }}
          >
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
                Create a Home
              </h3>
              <button
                type="button"
                onClick={() => setShowCreateHomeForm(false)}
                style={{
                  background: "transparent",
                  border: "none",
                  fontSize: "1.2rem",
                  color: "#6b7280",
                  cursor: "pointer",
                  fontWeight: "bold",
                }}
              >
                ✕
              </button>
            </div>

            <form
              onSubmit={submitNewHome}
              style={{ display: "flex", flexDirection: "column", gap: 12 }}
            >
              <div>
                <label
                  style={{
                    display: "block",
                    marginBottom: 4,
                    fontSize: "0.9rem",
                    fontWeight: 500,
                    color: "#374151",
                  }}
                >
                  Home Name *
                </label>
                <input
                  value={newHomeName}
                  onChange={(e) => setNewHomeName(e.target.value)}
                  placeholder="e.g., Main House"
                  required
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
                  disabled={creatingHome}
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
                  {creatingHome ? "Creating..." : "Create Home"}
                </button>
                <button
                  type="button"
                  onClick={() => setShowCreateHomeForm(false)}
                  disabled={creatingHome}
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

              {homeFormSuccess && (
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
                  {homeFormSuccess}
                </div>
              )}
              {homeFormError && (
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
                  {homeFormError}
                </div>
              )}
            </form>
          </div>
        </div>
      )}

      {/* ADD MEMBER POPUP MODAL */}
      {showAddMemberForm && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            width: "100vw",
            height: "100vh",
            background: "rgba(0,0,0,0.5)",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            zIndex: 9999,
          }}
        >
          <div
            style={{
              background: "white",
              padding: 24,
              borderRadius: 12,
              width: "100%",
              maxWidth: 420,
              boxShadow: "0 10px 25px rgba(0,0,0,0.2)",
            }}
          >
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
                Add a Member
              </h3>
              <button
                type="button"
                onClick={() => setShowAddMemberForm(false)}
                style={{
                  background: "transparent",
                  border: "none",
                  fontSize: "1.2rem",
                  color: "#6b7280",
                  cursor: "pointer",
                  fontWeight: "bold",
                }}
              >
                ✕
              </button>
            </div>

            <form
              onSubmit={submitAddMember}
              style={{ display: "flex", flexDirection: "column", gap: 12 }}
            >
              <div>
                <label
                  style={{
                    display: "block",
                    marginBottom: 4,
                    fontSize: "0.9rem",
                    fontWeight: 500,
                    color: "#374151",
                  }}
                >
                  Home *
                </label>
                <select
                  value={memberForm.homeId}
                  onChange={(e) =>
                    setMemberForm((prev) => ({
                      ...prev,
                      homeId: e.target.value,
                    }))
                  }
                  disabled={loadingHomes || homes.length === 0}
                  style={{
                    width: "100%",
                    padding: 8,
                    borderRadius: 6,
                    border: "1px solid #d1d5db",
                    background: "white",
                  }}
                >
                  <option value="">Select a home</option>
                  {homes.map((home) => (
                    <option key={home.home_id} value={home.home_id}>
                      {home.name}
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
                    color: "#374151",
                  }}
                >
                  Member Email *
                </label>
                <input
                  type="email"
                  value={memberForm.email}
                  onChange={(e) =>
                    setMemberForm((prev) => ({
                      ...prev,
                      email: e.target.value,
                    }))
                  }
                  placeholder="member@example.com"
                  required
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
                    color: "#374151",
                  }}
                >
                  Role
                </label>
                <select
                  value={memberForm.role}
                  onChange={(e) =>
                    setMemberForm((prev) => ({
                      ...prev,
                      role: e.target.value as UserType,
                    }))
                  }
                  style={{
                    width: "100%",
                    padding: 8,
                    borderRadius: 6,
                    border: "1px solid #d1d5db",
                    background: "white",
                  }}
                >
                  {MEMBER_ROLE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>

              <div
                style={{
                  fontSize: "0.8rem",
                  color: "#6b7280",
                  fontStyle: "italic",
                }}
              >
                Members must already have an account.
              </div>

              <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                <button
                  type="submit"
                  disabled={addingMember || !memberForm.homeId}
                  style={{
                    flex: 2,
                    background: "#10b981",
                    color: "white",
                    border: "none",
                    padding: "10px",
                    borderRadius: 6,
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  {addingMember ? "Adding..." : "Add Member"}
                </button>
                <button
                  type="button"
                  onClick={() => setShowAddMemberForm(false)}
                  disabled={addingMember}
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

              {memberFormSuccess && (
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
                  {memberFormSuccess}
                </div>
              )}
              {memberFormError && (
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
                  {memberFormError}
                </div>
              )}
            </form>
          </div>
        </div>
      )}

      {/* Top Header / Context Selection Bar */}
      <div
        style={{
          marginTop: 12,
          display: "flex",
          gap: 12,
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
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
          <button
            type="button"
            onClick={() => homeId && loadItems(homeId)}
            disabled={!homeId || loadingItems}
          >
            Refresh
          </button>
        </div>

        <button
          type="button"
          onClick={() => setIsAddModalOpen(true)}
          disabled={!homeId}
          style={{
            background: "#2563eb",
            color: "white",
            border: "none",
            padding: "8px 16px",
            borderRadius: 6,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          + Add New Item
        </button>
      </div>

      {error && <div style={{ color: "crimson", marginTop: 12 }}>{error}</div>}

      {/* Add Item Popup Modal Overlay */}
      {isAddModalOpen && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            background: "rgba(0,0,0,0.5)",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: "white",
              borderRadius: 12,
              width: "100%",
              maxWidth: 500,
              boxShadow: "0 10px 25px rgba(0,0,0,0.2)",
            }}
          >
            <AddInventory
              homeId={homeId}
              onCreated={() => {
                if (homeId) void loadItems(homeId);
              }}
              onCancel={() => setIsAddModalOpen(false)}
              onLogout={handleLogout}
            />
          </div>
        </div>
      )}

      {/* Inventory List Section */}
      <div style={{ marginTop: 24 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 16,
          }}
        >
          <div>
            <h4 style={{ margin: 0 }}>Inventory Items</h4>
            <span style={{ fontSize: "0.85rem", color: "#6b7280" }}>
              Total items: <strong>{items.length}</strong>
            </span>
          </div>

          {items.length > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <label
                style={{
                  fontSize: "0.9rem",
                  color: "#4b5563",
                  fontWeight: 500,
                }}
              >
                Sort by:
              </label>
              <select
                value={sortBy}
                onChange={(e) =>
                  setSortBy(e.target.value as "default" | "category" | "expiry")
                }
                style={{
                  padding: "4px 8px",
                  borderRadius: 6,
                  border: "1px solid #d1d5db",
                  background: "white",
                  fontSize: "0.9rem",
                }}
              >
                <option value="default">Default</option>
                <option value="category">Category</option>
                <option value="expiry">Expiry Date</option>
              </select>
            </div>
          )}
        </div>

        {loadingItems ? (
          <div>Loading inventory...</div>
        ) : sortedItems.length === 0 ? (
          <div>No inventory items found.</div>
        ) : (
          <div style={{ display: "grid", gap: 16 }}>
            {sortedItems.map((item) => {
              const isEditing = editingItemId === item.id;
              const isExpired =
                item.expiry_date && new Date(item.expiry_date) < new Date();
              const isHighlighted =
                highlightItemName &&
                item.name.toLowerCase().includes(highlightItemName);

              return (
                <div
                  key={item.id}
                  ref={(el) => {
                    if (el) {
                      itemRefs.current[item.id] = el;
                    } else {
                      delete itemRefs.current[item.id];
                    }
                  }}
                  style={{
                    border: isHighlighted
                      ? "2px solid #2563eb"
                      : "1px solid #e5e7eb",
                    borderRadius: 10,
                    padding: 16,
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: 12,
                    flexWrap: "wrap",
                    background: isHighlighted ? "#eff6ff" : "white",
                    boxShadow: "0 1px 3px rgba(0,0,0,0.02)",
                    transition: "background 0.5s ease, border 0.5s ease",
                  }}
                >
                  <div style={{ flex: 1, minWidth: 240 }}>
                    {isEditing ? (
                      <div style={{ display: "grid", gap: 8 }}>
                        <label
                          style={{
                            display: "grid",
                            gap: 4,
                            fontSize: "0.85rem",
                            fontWeight: 500,
                          }}
                        >
                          Name
                          <input
                            value={editValues.name}
                            readOnly
                            onChange={(e) =>
                              setEditValues((prev) => ({
                                ...prev,
                                name: e.target.value,
                              }))
                            }
                            style={{
                              padding: 6,
                              borderRadius: 4,
                              border: "1px solid #d1d5db",
                            }}
                          />
                        </label>
                        <div
                          style={{ display: "flex", flexWrap: "wrap", gap: 12 }}
                        >
                          <label
                            style={{
                              display: "grid",
                              gap: 4,
                              fontSize: "0.85rem",
                              fontWeight: 500,
                            }}
                          >
                            Category
                            <select
                              value={editValues.household_category_id}
                              onChange={(e) =>
                                setEditValues((prev) => ({
                                  ...prev,
                                  household_category_id: e.target.value,
                                }))
                              }
                              style={{
                                padding: 6,
                                borderRadius: 4,
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
                          </label>
                          <label
                            style={{
                              display: "grid",
                              gap: 4,
                              fontSize: "0.85rem",
                              fontWeight: 500,
                            }}
                          >
                            Quantity
                            <input
                              type="number"
                              min={0}
                              value={editValues.quantity}
                              onChange={(e) =>
                                setEditValues((prev) => ({
                                  ...prev,
                                  quantity:
                                    e.target.value === ""
                                      ? 0
                                      : Number(e.target.value),
                                }))
                              }
                              style={{
                                padding: 6,
                                borderRadius: 4,
                                border: "1px solid #d1d5db",
                              }}
                            />
                          </label>
                          <label
                            style={{
                              display: "grid",
                              gap: 4,
                              fontSize: "0.85rem",
                              fontWeight: 500,
                            }}
                          >
                            Unit
                            <input
                              value={editValues.unit}
                              onChange={(e) =>
                                setEditValues((prev) => ({
                                  ...prev,
                                  unit: e.target.value,
                                }))
                              }
                              style={{
                                padding: 6,
                                borderRadius: 4,
                                border: "1px solid #d1d5db",
                              }}
                            />
                          </label>
                        </div>
                        <label
                          style={{
                            display: "grid",
                            gap: 4,
                            fontSize: "0.85rem",
                            fontWeight: 500,
                          }}
                        >
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
                            style={{
                              padding: 6,
                              borderRadius: 4,
                              border: "1px solid #d1d5db",
                            }}
                          />
                        </label>
                        <label
                          style={{
                            display: "grid",
                            gap: 4,
                            fontSize: "0.85rem",
                            fontWeight: 500,
                          }}
                        >
                          Notes
                          <textarea
                            rows={2}
                            value={editValues.notes}
                            onChange={(e) =>
                              setEditValues((prev) => ({
                                ...prev,
                                notes: e.target.value,
                              }))
                            }
                            style={{
                              padding: 6,
                              borderRadius: 4,
                              border: "1px solid #d1d5db",
                            }}
                          />
                        </label>
                      </div>
                    ) : (
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: 4,
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                          }}
                        >
                          <strong
                            style={{ fontSize: "1.05rem", color: "#111827" }}
                          >
                            {item.name}
                          </strong>
                          <span
                            style={{
                              fontSize: "0.75rem",
                              fontWeight: 600,
                              color: "#4b5563",
                              background: "#f3f4f6",
                              padding: "2px 8px",
                              borderRadius: 12,
                              textTransform: "uppercase",
                            }}
                          >
                            {categoryName(item.household_category_id)}
                          </span>
                        </div>

                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 16,
                            fontSize: "0.9rem",
                            color: "#4b5563",
                            marginTop: 2,
                          }}
                        >
                          <div>
                            Quantity:{" "}
                            <strong>
                              {item.quantity} {item.unit}
                            </strong>
                          </div>
                          {item.expiry_date && (
                            <div
                              style={{
                                color: isExpired ? "#dc2626" : "#6b7280",
                                fontWeight: isExpired ? 600 : 400,
                              }}
                            >
                              Expires: {item.expiry_date}{" "}
                              {isExpired && "(Expired)"}
                            </div>
                          )}
                        </div>

                        {item.notes && (
                          <div
                            style={{
                              fontSize: "0.8rem",
                              color: "#9ca3af",
                              fontStyle: "italic",
                              marginTop: 2,
                            }}
                          >
                            Note: {item.notes}
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
                          style={{
                            background: "#059669",
                            color: "white",
                            border: "none",
                            padding: "6px 12px",
                            borderRadius: 4,
                            cursor: "pointer",
                            fontSize: "0.85rem",
                          }}
                        >
                          {savingItemId === item.id ? "Saving..." : "Save"}
                        </button>
                        <button
                          type="button"
                          onClick={cancelEdit}
                          disabled={savingItemId === item.id}
                          style={{
                            background: "#e5e7eb",
                            color: "#374151",
                            border: "none",
                            padding: "6px 12px",
                            borderRadius: 4,
                            cursor: "pointer",
                            fontSize: "0.85rem",
                          }}
                        >
                          Cancel
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => startEdit(item)}
                          disabled={
                            Boolean(editingItemId) && editingItemId !== item.id
                          }
                          style={{
                            background: "none",
                            border: "1px solid #d1d5db",
                            color: "#2563eb",
                            padding: "6px 10px",
                            borderRadius: 4,
                            cursor: "pointer",
                            fontSize: "0.85rem",
                          }}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(item)}
                          disabled={
                            deletingItemId === item.id ||
                            (Boolean(editingItemId) &&
                              editingItemId !== item.id)
                          }
                          style={{
                            background: "none",
                            border: "1px solid #d1d5db",
                            color: "#dc2626",
                            padding: "6px 10px",
                            borderRadius: 4,
                            cursor: "pointer",
                            fontSize: "0.85rem",
                          }}
                        >
                          {deletingItemId === item.id
                            ? "Deleting..."
                            : "Delete"}
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
