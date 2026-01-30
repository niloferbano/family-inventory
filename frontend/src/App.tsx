import React, { useCallback, useState } from "react";
import Login from "./components/Login";
import AddEvent from "./components/AddEvent";
import { getToken, clearToken } from "./api/auth";

export default function App() {
  const [authed, setAuthed] = useState<boolean>(() => Boolean(getToken()));

  const onLogin = useCallback(() => setAuthed(true), []);
  const onLogout = useCallback(() => { clearToken(); setAuthed(false); }, []);

  return (
    <div>
      <header style={{ padding: 12, borderBottom: "1px solid #eee" }}>
        <h2 style={{ margin: 0 }}>Family Inventory — Notifications</h2>
      </header>

      <main>
        {authed ? <AddEvent onLogout={onLogout} /> : <Login onLogin={onLogin} />}
      </main>
    </div>
  );
}