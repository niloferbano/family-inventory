import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
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

const INVENTORY_TOPIC_OPTIONS = [
  {
    key: "expiring_soon",
    label: "Expiring soon",
    topic: "inventory.item.expiring_soon",
  },
  {
    key: "expired",
    label: "Expired",
    topic: "inventory.item.expired",
  },
] as const;

type InventoryTopicKey = (typeof INVENTORY_TOPIC_OPTIONS)[number]["key"];

const TOPIC_BY_KEY: Record<InventoryTopicKey, string> = {
  expiring_soon: "inventory.item.expiring_soon",
  expired: "inventory.item.expired",
};

const LABEL_BY_KEY: Record<InventoryTopicKey, string> = {
  expiring_soon: "Expiring soon",
  expired: "Expired",
};

const KEY_BY_TOPIC: Record<string, InventoryTopicKey> = {
  [TOPIC_BY_KEY.expiring_soon]: "expiring_soon",
  [TOPIC_BY_KEY.expired]: "expired",
};

const DEFAULT_TOPIC_KEY: InventoryTopicKey = "expiring_soon";

const topicLabelFor = (topic: string) => {
  const key = KEY_BY_TOPIC[topic];
  return key ? LABEL_BY_KEY[key] : "Other notification";
};

const topicKeyFor = (topic: string): InventoryTopicKey | null => {
  return KEY_BY_TOPIC[topic] ?? null;
};

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
    topicKey: DEFAULT_TOPIC_KEY,
    channel: "inapp" as NotificationChannel,
    enabled: true,
  });
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValues, setEditValues] = useState({
    topicKey: DEFAULT_TOPIC_KEY,
    channel: "inapp" as NotificationChannel,
    enabled: true,
  });
  const [editingUnsupported, setEditingUnsupported] = useState(false);
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
    setCreating(true);
    try {
      await createSubscription({
        homeId: form.homeId,
        topic: TOPIC_BY_KEY[form.topicKey],
        channel: form.channel,
        enabled: form.enabled,
      });
      setForm((prev) => ({
        ...prev,
        topicKey: DEFAULT_TOPIC_KEY,
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
    const topicKey = topicKeyFor(sub.topic);
    setEditingId(sub.id);
    setEditingUnsupported(topicKey === null);
    setEditValues({
      topicKey: topicKey ?? DEFAULT_TOPIC_KEY,
      channel: sub.channel,
      enabled: sub.enabled,
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditingUnsupported(false);
  };

  const saveEdit = async () => {
    if (!editingId) {
      return;
    }
    if (editingUnsupported) {
      setError("This subscription type can't be edited here. Delete and recreate it.");
      return;
    }
    setSavingId(editingId);
    setError(null);
    try {
      await updateSubscription(editingId, {
        topic: TOPIC_BY_KEY[editValues.topicKey],
        channel: editValues.channel,
        enabled: editValues.enabled,
      });
      setEditingId(null);
      setEditingUnsupported(false);
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
    const label = topicLabelFor(sub.topic);
    if (!window.confirm(`Delete subscription for ${label}?`)) {
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
            Manage which inventory alerts you receive per home.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Link to="/" style={{ textDecoration: "none" }}>
            Home
          </Link>
          <button type="button" onClick={handleLogout}>
            Logout
          </button>
        </div>
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
            Alert type
            <select
              value={form.topicKey}
              onChange={(e) =>
                setForm((prev) => ({
                  ...prev,
                  topicKey: e.target.value as InventoryTopicKey,
                }))
              }
            >
              {INVENTORY_TOPIC_OPTIONS.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>
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
              const topicLabel = topicLabelFor(sub.topic);
              const isSupportedTopic = topicKeyFor(sub.topic) !== null;
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
                      <div style={{ fontWeight: 600 }}>{topicLabel}</div>
                      <div style={{ fontSize: 12, color: "#555", marginTop: 4 }}>
                        Home: {homeName} · Channel: {sub.channel} ·{" "}
                        {sub.enabled ? "Enabled" : "Disabled"}
                        {!isSupportedTopic && " · Unsupported type"}
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button
                        type="button"
                        onClick={() => startEdit(sub)}
                        disabled={!isSupportedTopic || (Boolean(editingId) && !isEditing)}
                        title={!isSupportedTopic ? "Unsupported notification type" : undefined}
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
                        Alert type
                        <select
                          value={editValues.topicKey}
                          onChange={(e) =>
                            setEditValues((prev) => ({
                              ...prev,
                              topicKey: e.target.value as InventoryTopicKey,
                            }))
                          }
                          disabled={editingUnsupported}
                        >
                          {INVENTORY_TOPIC_OPTIONS.map((option) => (
                            <option key={option.key} value={option.key}>
                              {option.label}
                            </option>
                          ))}
                        </select>
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
                      {editingUnsupported && (
                        <div style={{ color: "#555" }}>
                          This subscription uses a custom alert type. Delete and recreate it.
                        </div>
                      )}
                      <div style={{ display: "flex", gap: 8 }}>
                        <button
                          type="button"
                          onClick={saveEdit}
                          disabled={savingId === sub.id || editingUnsupported}
                        >
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
