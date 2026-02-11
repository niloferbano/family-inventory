import React, { useCallback, useEffect, useMemo, useState } from "react";
import { clearToken } from "../api/auth";
import { HomeSummary, listHomes } from "../api/homes";
import {
  NotificationChannel,
  NotificationSubscription,
  createSubscription,
  deleteSubscription,
  listSubscriptions,
  updateSubscription,
} from "../api/notifications";

const CHANNEL_OPTIONS: Array<{ value: NotificationChannel; label: string }> = [
  { value: "inapp", label: "In-app" },
  { value: "email", label: "Email" },
  { value: "sms", label: "SMS" },
  { value: "push", label: "Push" },
  { value: "log", label: "Log" },
];

const isUnauthorized = (err: unknown) => {
  const message = String(err ?? "");
  return message.includes("401") || message.toLowerCase().includes("unauthorized");
};

export default function NotificationSubscriptions({
  onLogout,
}: {
  onLogout: () => void;
}) {
  const [homes, setHomes] = useState<HomeSummary[]>([]);
  const [loadingHomes, setLoadingHomes] = useState(true);
  const [subscriptions, setSubscriptions] = useState<NotificationSubscription[]>([]);
  const [loadingSubscriptions, setLoadingSubscriptions] = useState(true);
  const [filterHomeId, setFilterHomeId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    homeId: "",
    topic: "",
    channel: "inapp" as NotificationChannel,
    enabled: true,
  });
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValues, setEditValues] = useState({
    topic: "",
    channel: "inapp" as NotificationChannel,
    enabled: true,
  });
  const [savingId, setSavingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleLogout = useCallback(() => {
    clearToken();
    onLogout();
  }, [onLogout]);

  const loadHomes = useCallback(async () => {
    setLoadingHomes(true);
    try {
      const homesList = await listHomes();
      setHomes(homesList);
      if (homesList.length > 0) {
        setForm((prev) => ({
          ...prev,
          homeId: prev.homeId || homesList[0].home_id,
        }));
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

  const loadSubscriptions = useCallback(
    async (homeId?: string) => {
      setLoadingSubscriptions(true);
      setError(null);
      try {
        const data = await listSubscriptions(homeId);
        setSubscriptions(data);
      } catch (err) {
        if (isUnauthorized(err)) {
          handleLogout();
          return;
        }
        setError((err as Error)?.message ?? "Failed to load subscriptions.");
      } finally {
        setLoadingSubscriptions(false);
      }
    },
    [handleLogout]
  );

  useEffect(() => {
    loadHomes();
  }, [loadHomes]);

  useEffect(() => {
    loadSubscriptions(filterHomeId || undefined);
  }, [filterHomeId, loadSubscriptions]);

  const homesById = useMemo(() => {
    return new Map(homes.map((home) => [home.home_id, home.name]));
  }, [homes]);

  const submitCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormError(null);
    setFormSuccess(null);
    if (!form.homeId) {
      setFormError("Select a home to subscribe to.");
      return;
    }
    if (!form.topic.trim()) {
      setFormError("Topic is required.");
      return;
    }
    setCreating(true);
    try {
      await createSubscription({
        homeId: form.homeId,
        topic: form.topic.trim(),
        channel: form.channel,
        enabled: form.enabled,
      });
      setForm((prev) => ({
        ...prev,
        topic: "",
        channel: "inapp",
        enabled: true,
      }));
      setFormSuccess("Subscription added.");
      await loadSubscriptions(filterHomeId || undefined);
    } catch (err) {
      if (isUnauthorized(err)) {
        handleLogout();
        return;
      }
      setFormError((err as Error)?.message ?? "Failed to create subscription.");
    } finally {
      setCreating(false);
    }
  };

  const startEdit = (sub: NotificationSubscription) => {
    setEditingId(sub.id);
    setEditValues({
      topic: sub.topic,
      channel: sub.channel,
      enabled: sub.enabled,
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
  };

  const saveEdit = async () => {
    if (!editingId) {
      return;
    }
    if (!editValues.topic.trim()) {
      setError("Topic is required.");
      return;
    }
    setSavingId(editingId);
    setError(null);
    try {
      await updateSubscription(editingId, {
        topic: editValues.topic.trim(),
        channel: editValues.channel,
        enabled: editValues.enabled,
      });
      setEditingId(null);
      await loadSubscriptions(filterHomeId || undefined);
    } catch (err) {
      if (isUnauthorized(err)) {
        handleLogout();
        return;
      }
      setError((err as Error)?.message ?? "Failed to update subscription.");
    } finally {
      setSavingId(null);
    }
  };

  const removeSubscription = async (sub: NotificationSubscription) => {
    if (!window.confirm(`Delete subscription for ${sub.topic}?`)) {
      return;
    }
    setDeletingId(sub.id);
    setError(null);
    try {
      await deleteSubscription(sub.id);
      await loadSubscriptions(filterHomeId || undefined);
    } catch (err) {
      if (isUnauthorized(err)) {
        handleLogout();
        return;
      }
      setError((err as Error)?.message ?? "Failed to delete subscription.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div style={{ maxWidth: 960, margin: "1rem auto", padding: 16 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          gap: 12,
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <div>
          <h3 style={{ margin: 0 }}>Notification Subscriptions</h3>
          <p style={{ margin: "4px 0 0", color: "#555" }}>
            Manage which notification topics you receive per home.
          </p>
        </div>
        <button type="button" onClick={handleLogout}>
          Logout
        </button>
      </div>

      <div
        style={{
          marginTop: 16,
          padding: 16,
          borderRadius: 12,
          border: "1px solid #eee",
          background: "#fff",
        }}
      >
        <h4 style={{ margin: "0 0 12px" }}>Add subscription</h4>
        <form onSubmit={submitCreate} style={{ display: "grid", gap: 12 }}>
          <label style={{ display: "grid", gap: 6 }}>
            Home
            <select
              value={form.homeId}
              onChange={(e) => setForm((prev) => ({ ...prev, homeId: e.target.value }))}
              disabled={loadingHomes || homes.length === 0}
            >
              {homes.length === 0 && <option value="">No homes available</option>}
              {homes.map((home) => (
                <option key={home.home_id} value={home.home_id}>
                  {home.name}
                </option>
              ))}
            </select>
          </label>

          <label style={{ display: "grid", gap: 6 }}>
            Topic
            <input
              value={form.topic}
              onChange={(e) => setForm((prev) => ({ ...prev, topic: e.target.value }))}
              placeholder="inventory.item.*"
              required
            />
          </label>

          <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
            <label style={{ display: "grid", gap: 6 }}>
              Channel
              <select
                value={form.channel}
                onChange={(e) =>
                  setForm((prev) => ({
                    ...prev,
                    channel: e.target.value as NotificationChannel,
                  }))
                }
              >
                {CHANNEL_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(e) => setForm((prev) => ({ ...prev, enabled: e.target.checked }))}
              />
              Enabled
            </label>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button type="submit" disabled={creating}>
              {creating ? "Saving..." : "Add subscription"}
            </button>
            {formError && <span style={{ color: "crimson" }}>{formError}</span>}
            {formSuccess && <span style={{ color: "green" }}>{formSuccess}</span>}
          </div>
        </form>
      </div>

      <div style={{ marginTop: 24 }}>
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 12,
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <h4 style={{ margin: 0 }}>Your subscriptions</h4>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              Home
              <select
                value={filterHomeId}
                onChange={(e) => setFilterHomeId(e.target.value)}
                disabled={loadingHomes}
              >
                <option value="">All homes</option>
                {homes.map((home) => (
                  <option key={home.home_id} value={home.home_id}>
                    {home.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={() => loadSubscriptions(filterHomeId || undefined)}
              disabled={loadingSubscriptions}
            >
              Refresh
            </button>
          </div>
        </div>

        {error && <div style={{ color: "crimson", marginTop: 12 }}>{error}</div>}

        {loadingSubscriptions ? (
          <div style={{ marginTop: 12 }}>Loading subscriptions...</div>
        ) : subscriptions.length === 0 ? (
          <div style={{ marginTop: 12, color: "#555" }}>
            No subscriptions found for this account.
          </div>
        ) : (
          <div style={{ marginTop: 12, display: "grid", gap: 12 }}>
            {subscriptions.map((sub) => {
              const isEditing = editingId === sub.id;
              const homeName = homesById.get(sub.home_id) ?? sub.home_id;
              return (
                <div
                  key={sub.id}
                  style={{
                    border: "1px solid #eee",
                    borderRadius: 10,
                    padding: 12,
                    background: "#fff",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 12,
                      flexWrap: "wrap",
                      alignItems: "center",
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600 }}>{sub.topic}</div>
                      <div style={{ fontSize: 12, color: "#555", marginTop: 4 }}>
                        Home: {homeName} · Channel: {sub.channel} ·{" "}
                        {sub.enabled ? "Enabled" : "Disabled"}
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button
                        type="button"
                        onClick={() => startEdit(sub)}
                        disabled={Boolean(editingId) && !isEditing}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => removeSubscription(sub)}
                        disabled={deletingId === sub.id}
                      >
                        {deletingId === sub.id ? "Deleting..." : "Delete"}
                      </button>
                    </div>
                  </div>

                  {isEditing && (
                    <div style={{ marginTop: 12, display: "grid", gap: 12 }}>
                      <label style={{ display: "grid", gap: 6 }}>
                        Topic
                        <input
                          value={editValues.topic}
                          onChange={(e) =>
                            setEditValues((prev) => ({ ...prev, topic: e.target.value }))
                          }
                        />
                      </label>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
                        <label style={{ display: "grid", gap: 6 }}>
                          Channel
                          <select
                            value={editValues.channel}
                            onChange={(e) =>
                              setEditValues((prev) => ({
                                ...prev,
                                channel: e.target.value as NotificationChannel,
                              }))
                            }
                          >
                            {CHANNEL_OPTIONS.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <input
                            type="checkbox"
                            checked={editValues.enabled}
                            onChange={(e) =>
                              setEditValues((prev) => ({
                                ...prev,
                                enabled: e.target.checked,
                              }))
                            }
                          />
                          Enabled
                        </label>
                      </div>
                      <div style={{ display: "flex", gap: 8 }}>
                        <button type="button" onClick={saveEdit} disabled={savingId === sub.id}>
                          {savingId === sub.id ? "Saving..." : "Save"}
                        </button>
                        <button type="button" onClick={cancelEdit} disabled={savingId === sub.id}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
