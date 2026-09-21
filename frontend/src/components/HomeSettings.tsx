import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { API_BASE, getToken } from "../api/auth";
import { HomeMember } from "../api/homes";

type Category = { id: string; name: string; item_count: number };
type Settings = { home_id: string; name: string; members: HomeMember[]; categories: Category[] };

async function request<T>(path: string, method = "GET", body?: object): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method, headers: { Authorization: `bearer ${getToken()}`, "Content-Type": "application/json" },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const detail = Array.isArray(data?.detail) ? data.detail.map((d: { msg: string }) => d.msg).join("; ") : data?.detail;
    throw new Error(data?.message || detail || `Request failed (${response.status}).`);
  }
  return data;
}

export default function HomeSettings() {
  const { homeId } = useParams();
  const base = `/homes/${homeId}/settings`;
  const [settings, setSettings] = useState<Settings | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("residence");
  const [categoryName, setCategoryName] = useState("");
  const [categoryDrafts, setCategoryDrafts] = useState<Record<string, string>>({});
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setSettings(null); setError("");
    request<Settings>(base).then(data => {
      if (!cancelled) { setSettings(data); setName(data.name); }
    }).catch(e => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [base, retry]);

  async function mutate(path: string, method: string, body: object | undefined, success: string, after?: () => void) {
    if (pending) return;
    setPending(true); setError(""); setMessage("");
    try {
      await request(path, method, body);
      after?.();
      setSettings(await request<Settings>(base));
      setMessage(success);
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to save changes."); }
    finally { setPending(false); }
  }

  return <section style={{ maxWidth: 800, margin: "24px auto", padding: 16 }}>
    <Link to={`/?home=${homeId}`}>Back to inventory</Link>
    <h1>Home settings</h1>
    {error && <p role="alert" style={{ color: "#b00020" }}>{error}</p>}
    {message && <p role="status">{message}</p>}
    {!settings ? <>{!error ? <p>Loading settings…</p> : <button onClick={() => setRetry(n => n + 1)}>Retry</button>}</> : <>
      <form onSubmit={e => { e.preventDefault(); void mutate(base, "PATCH", { name: name.trim() }, "Home name saved."); }}>
        <h2>Basic details</h2>
        <fieldset disabled={pending} style={{ border: 0, padding: 0 }}>
          <label>Home name <input required minLength={2} maxLength={100} value={name} onChange={e => setName(e.target.value)} /></label>
          <button>Save name</button>
        </fieldset>
      </form>
      <h2>Members</h2>
      <p>Owners are protected. Members can be residents or guests.</p>
      <ul>{settings.members.map(member => <li key={member.user_id} style={{ marginBottom: 12 }}>
        {member.username} ({member.email}) {member.user_type === "owner" ? <strong>Owner</strong> : <>
          <select aria-label={`Role for ${member.username}`} value={member.user_type} disabled={pending}
            onChange={e => void mutate(`${base}/members/${member.user_id}`, "PATCH", { user_type: e.target.value }, "Member role updated.")}>
            <option value="residence">Resident</option><option value="guest">Guest</option>
          </select>
          <button disabled={pending} onClick={() => { if (window.confirm(`Remove ${member.username} from this home?`)) void mutate(`${base}/members/${member.user_id}`, "DELETE", undefined, "Member removed."); }}>Remove</button>
        </>}
      </li>)}</ul>
      <form onSubmit={e => { e.preventDefault(); void mutate(`${base}/members`, "POST", { user_email: email.trim(), user_type: role }, "Member added.", () => setEmail("")); }}>
        <fieldset disabled={pending} style={{ border: 0, padding: 0 }}>
          <label>Member email <input type="email" required value={email} onChange={e => setEmail(e.target.value)} /></label>
          <select aria-label="New member role" value={role} onChange={e => setRole(e.target.value)}><option value="residence">Resident</option><option value="guest">Guest</option></select>
          <button>Add member</button>
        </fieldset>
      </form>
      <h2>Categories</h2>
      {!settings.categories.length && <p>No categories yet. Create one to start adding inventory.</p>}
      {settings.categories.map(category => <form key={category.id} style={{ marginBottom: 12 }} onSubmit={e => {
        e.preventDefault(); void mutate(`${base}/categories/${category.id}`, "PATCH", { name: (categoryDrafts[category.id] ?? category.name).trim() }, "Category saved.");
      }}>
        <fieldset disabled={pending} style={{ border: 0, padding: 0 }}>
          <label>Category name <input required maxLength={60} value={categoryDrafts[category.id] ?? category.name}
            onChange={e => setCategoryDrafts(prev => ({ ...prev, [category.id]: e.target.value }))} /></label>
          <span> {category.item_count} inventory items </span><button>Save</button>
          <button type="button" disabled={category.item_count > 0} onClick={() => {
            if (window.confirm(`Delete category “${category.name}”?`)) void mutate(`${base}/categories/${category.id}`, "DELETE", undefined, "Category deleted.");
          }}>Delete</button>
          {category.item_count > 0 && <small> Move inventory items to another category before deleting.</small>}
        </fieldset>
      </form>)}
      <form onSubmit={e => { e.preventDefault(); void mutate(`/homes/${homeId}/categories`, "POST", { name: categoryName.trim() }, "Category created.", () => setCategoryName("")); }}>
        <fieldset disabled={pending} style={{ border: 0, padding: 0 }}>
          <label>New category <input required maxLength={60} value={categoryName} onChange={e => setCategoryName(e.target.value)} /></label>
          <button>Create category</button>
        </fieldset>
      </form>
    </>}
  </section>;
}
