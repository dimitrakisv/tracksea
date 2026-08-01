import { appCopy } from "../app/copy";
import "./SystemStatus.css";

export function SystemStatus() {
  return (
    <main className="system-status" aria-labelledby="app-title">
      <section className="system-status__content">
        <p className="system-status__eyebrow">Sprint 1</p>
        <h1 id="app-title">{appCopy.name}</h1>
        <p className="system-status__tagline">{appCopy.tagline}</p>
        <p className="system-status__state">{appCopy.status}</p>
      </section>
    </main>
  );
}
