import { useEffect, useState } from "react";
import { api } from "../api/client";
import { HeroAtmosphere } from "./HeroAtmosphere";

type Navigate = (path: string) => void;

export function HomePage({ onNavigate }: { onNavigate: Navigate }) {
  const [count, setCount] = useState<number | null>(null);
  const [logical, setLogical] = useState<number | null>(null);
  const [gaps, setGaps] = useState<number | null>(null);

  useEffect(() => {
    api
      .health()
      .then((h) => {
        setCount(h.concrete_count);
        setLogical(h.logical_count);
      })
      .catch(() => undefined);
    api
      .coverage()
      .then((c) => setGaps(c.gap_count))
      .catch(() => undefined);
  }, []);

  const openApp = () => onNavigate("/app");

  return (
    <div className="sf-home">
      <nav className="sf-topnav">
        <a
          className="sf-brand"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            onNavigate("/");
          }}
        >
          SignalForge
        </a>
        <div className="sf-topnav-actions">
          <a
            href="/app"
            className="sf-link"
            onClick={(e) => {
              e.preventDefault();
              openApp();
            }}
          >
            Scenario viewer
          </a>
          <button type="button" className="sf-btn sf-btn-primary" onClick={openApp}>
            Explore scenarios
          </button>
        </div>
      </nav>

      <section className="sf-hero">
        <div className="sf-hero-copy">
          <p className="sf-brand-hero">
            Signal<span>Forge</span>
          </p>
          <h1>Grounded AV scenarios you can audit end to end.</h1>
          <p className="sf-hero-lead">
            Synthetic lidar and radar over 2,200 concrete cases, each traced to regulation,
            crash typology, or a real ADS incident.
          </p>
          <div className="sf-cta-group">
            <button type="button" className="sf-btn sf-btn-primary sf-btn-lg" onClick={openApp}>
              Explore scenarios
            </button>
            <a
              href="#provenance"
              className="sf-btn sf-btn-ghost sf-btn-lg"
              onClick={(e) => {
                e.preventDefault();
                document.getElementById("provenance")?.scrollIntoView({ behavior: "smooth" });
              }}
            >
              See provenance
            </a>
          </div>
        </div>
        <HeroAtmosphere />
      </section>

      <section className="sf-section" id="what">
        <div className="sf-section-inner">
          <h2>What it is</h2>
          <p>
            SignalForge is an AV scenario benchmark built for teams that need coverage they can
            defend. Logical families expand into concrete ODD variants with kinematic criticality,
            then a NumPy lidar/radar layer renders the scene for inspection.
          </p>
        </div>
      </section>

      <section className="sf-section sf-section-alt" id="provenance">
        <div className="sf-section-inner">
          <h2>Provenance first</h2>
          <p>
            No free-invented prompts. Every scenario links to NHTSA pre-crash typology, UNECE R157
            parameters, Euro NCAP VRU protocols, HAZOP sensor degradation, or NHTSA SGO incident
            narratives, including an explicit gap list for unmatched reports.
          </p>
          <ul className="sf-source-list">
            <li>NHTSA pre-crash groups + crash-frequency weights</li>
            <li>UNECE R157 cut-in / cut-out / deceleration</li>
            <li>Euro NCAP CPNA / CPFA / CPTA</li>
            <li>HAZOP lidar/radar degradation cases</li>
            <li>NHTSA SGO ADS incident classification</li>
          </ul>
        </div>
      </section>

      <section className="sf-section" id="coverage">
        <div className="sf-section-inner">
          <h2>Coverage at a glance</h2>
          <p>Live counts from the SignalForge API.</p>
          <div className="sf-coverage-row" role="list">
            <div className="sf-coverage-item" role="listitem">
              <span className="sf-coverage-n">{count ?? "-"}</span>
              <span className="sf-coverage-l">concrete scenarios</span>
            </div>
            <div className="sf-coverage-item" role="listitem">
              <span className="sf-coverage-n">{logical ?? "-"}</span>
              <span className="sf-coverage-l">logical families</span>
            </div>
            <div className="sf-coverage-item" role="listitem">
              <span className="sf-coverage-n">{gaps ?? "-"}</span>
              <span className="sf-coverage-l">SGO gap candidates</span>
            </div>
          </div>
        </div>
      </section>

      <section className="sf-section sf-section-cta">
        <div className="sf-section-inner">
          <h2>Open the scenario viewer</h2>
          <p>Filter by family, weather, and difficulty. Play synthetic lidar with full provenance.</p>
          <button type="button" className="sf-btn sf-btn-primary sf-btn-lg" onClick={openApp}>
            Launch viewer
          </button>
        </div>
      </section>

      <footer className="sf-footer">
        <a
          className="sf-brand"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            onNavigate("/");
          }}
        >
          SignalForge
        </a>
        <span>Auditable AV scenario benchmark</span>
      </footer>
    </div>
  );
}
