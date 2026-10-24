import { useRef } from "react";
import { Link } from "react-router-dom";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";
import { ThemeToggle } from "../ui/ThemeToggle";

gsap.registerPlugin(ScrollTrigger, useGSAP);

const BARS: [string, number, string][] = [
  ["Labour", 70, "#59c793"],
  ["Parts", 52, "#3fb5c8"],
  ["Call-out", 26, "#e9b949"],
  ["Margin", 30, "#129a8d"],
];

const ic = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round", viewBox: "0 0 24 24", "aria-hidden": true } as const;
const TRADES: { name: string; icon: React.ReactNode }[] = [
  { name: "Plumbers", icon: <svg {...ic}><path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z" /></svg> },
  { name: "Electricians", icon: <svg {...ic}><path d="M13 2 4 14h7l-1 8 9-12h-7z" /></svg> },
  { name: "Painters", icon: <svg {...ic}><rect x="4" y="3" width="14" height="5" rx="1.5" /><path d="M18 5.5h2v5H12v4M10.5 14.5h3v7h-3z" /></svg> },
  { name: "Builders", icon: <svg {...ic}><path d="M3 21h18M5 21V9l7-5 7 5v12M10 21v-6h4v6" /></svg> },
  { name: "Cleaners", icon: <svg {...ic}><path d="M12 3v8M9 11h6l1 10H8zM7 3l1.5 3M17 3l-1.5 3" /></svg> },
];

export default function Landing() {
  const root = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const mm = gsap.matchMedia();

      mm.add("(prefers-reduced-motion: no-preference)", () => {
        const q = gsap.utils.selector(root);
        const tapeSec = root.current!.querySelector<HTMLElement>(".tapesec")!;
        const flow = root.current!.querySelector<HTMLElement>(".flow")!;
        tapeSec.classList.add("live");
        flow.classList.add("live");

        // The one orchestrated moment: the hero lands once.
        gsap
          .timeline({ defaults: { ease: "power3.out" } })
          .from(q(".hero h1 .ln > span"), { yPercent: 110, duration: 0.9, stagger: 0.12 })
          .from(q(".hero .lede, .hero-actions, .trades"), { autoAlpha: 0, y: 16, duration: 0.6, stagger: 0.1 }, "-=0.4")
          .from(q(".ticket.you"), { y: -120, rotate: -12, autoAlpha: 0, duration: 0.9 }, 0.2)
          .from(q(".ticket.them"), { y: 140, rotate: 10, autoAlpha: 0, duration: 0.9 }, 0.45);

        // A tape measure pulls across the job and reveals the single number.
        const fill = q(".tape-fill")[0];
        const tape = q(".tape")[0];
        const end = q(".tape-end")[0];
        gsap.set(fill, { clipPath: "inset(0 100% 0 0)" });
        gsap.set(tape, { scaleX: 0, transformOrigin: "left center" });
        gsap
          .timeline({
            scrollTrigger: { trigger: tapeSec, start: "top top", end: "+=110%", scrub: 0.6, pin: true, invalidateOnRefresh: true },
          })
          .to(fill, { clipPath: "inset(0 0% 0 0)", ease: "none" }, 0)
          .to(tape, { scaleX: 1, ease: "none" }, 0)
          .fromTo(end, { x: 0 }, { x: () => tapeSec.clientWidth - 18, ease: "none" }, 0);

        // Three steps, one pinned stage.
        const steps = q(".flow-step");
        const cards = q(".stage-card");
        gsap.set([steps.slice(1), cards.slice(1)], { autoAlpha: 0 });
        gsap.set(q(".wa .msg"), { autoAlpha: 0, y: 14 });
        gsap.set(q(".sheet .bar i"), { scaleX: 0, transformOrigin: "left center" });
        gsap.set(q(".sheet .ask"), { autoAlpha: 0, y: 10 });
        gsap.set(q(".final-bubble"), { autoAlpha: 0, scale: 0.9, y: 20 });
        const tl = gsap.timeline({
          scrollTrigger: { trigger: flow, start: "top top", end: "+=260%", scrub: 0.6, pin: true },
          defaults: { ease: "none" },
        });
        tl.to(q(".wa .msg"), { autoAlpha: 1, y: 0, stagger: 0.25, duration: 0.5 })
          .to([steps[0], cards[0]], { autoAlpha: 0, duration: 0.3 }, "+=0.4")
          .to([steps[1], cards[1]], { autoAlpha: 1, duration: 0.3 }, "<")
          .to(q(".sheet .bar i"), { scaleX: 1, stagger: 0.15, duration: 0.5 })
          .to(q(".sheet .ask"), { autoAlpha: 1, y: 0, duration: 0.4 })
          .to([steps[1], cards[1]], { autoAlpha: 0, duration: 0.3 }, "+=0.4")
          .to([steps[2], cards[2]], { autoAlpha: 1, duration: 0.3 }, "<")
          .to(q(".final-bubble"), { autoAlpha: 1, scale: 1, y: 0, duration: 0.6, ease: "back.out(1.6)" })
          .to({}, { duration: 0.5 });

        return () => {
          tapeSec.classList.remove("live");
          flow.classList.remove("live");
        };
      });
    },
    { scope: root },
  );

  return (
    <div className="land" ref={root}>
      <header className="land-nav">
        <Link to="/" className="brand">
          <img className="brand-mark" src="/logo.png" alt="" />
          Gesir
        </Link>
        <div className="right">
          <ThemeToggle />
          <Link to="/app" className="btn small primary">
            Open dashboard
          </Link>
        </div>
      </header>

      <section className="hero" aria-labelledby="h">
        <div>
          <h1 id="h">
            <span className="ln"><span>Gesir talks.</span></span>
            <span className="ln"><span>You decide.</span></span>
          </h1>
          <p className="lede">
            Link your WhatsApp number and Gesir chats with your customers on your behalf. It finds out what the job is,
            drafts a price, and asks your permission before anything is sent.
          </p>
          <div className="hero-actions">
            <Link to="/app" className="btn primary">
              Open dashboard
            </Link>
            <a href="#how" className="btn">
              See how it works
            </a>
          </div>
          <ul className="trades" aria-label="Built for trades">
            {TRADES.map((t) => (
              <li key={t.name}>
                {t.icon}
                {t.name}
              </li>
            ))}
          </ul>
        </div>
        <div className="tickets" aria-hidden="true">
          <div className="ticket you">
            <div className="ticket-head"><b>Job 0412</b><span>Kitchen sink leak</span></div>
            <div className="swatch">
              {BARS.map(([n, w, c]) => (
                <div className="mini-bar" key={n}>
                  <span>{n}</span>
                  <i style={{ "--w": `${w}%`, "--c": c } as React.CSSProperties} />
                </div>
              ))}
            </div>
            <div className="label">
              <b>What you see</b>
              <span>Every line of the sum</span>
            </div>
          </div>
          <div className="ticket them">
            <div className="ticket-head"><b>WhatsApp</b><span>Sent by Gesir</span></div>
            <div className="swatch">
              <div className="bubble">
                Your price is
                <strong className="num">RM 380.00</strong>
              </div>
            </div>
            <div className="label">
              <b>What they get</b>
              <span>One number, after your yes</span>
            </div>
          </div>
        </div>
      </section>

      <div className="hazard" aria-hidden="true" />

      <section className="tapesec" aria-label="The customer only sees the total">
        <div className="tape-base">
          <h2>Every job is a sum.</h2>
        </div>
        <div className="tape-fill">
          <h2>The customer sees one number.</h2>
          <p>Labour, parts and margin stay with you. Gesir sends nothing without your yes.</p>
        </div>
        <div className="tape" aria-hidden="true" />
        <div className="tape-end" aria-hidden="true" />
      </section>

      <section className="flow" id="how" aria-label="How it works">
        <div className="flow-inner">
          <div className="flow-steps">
            <div className="flow-step">
              <span className="n">Step 1</span>
              <h3>Gesir chats for you</h3>
              <p>From your own WhatsApp number it asks one question at a time: what is wrong, where, how big, and when suits.</p>
            </div>
            <div className="flow-step">
              <span className="n">Step 2</span>
              <h3>Gesir asks you first</h3>
              <p>You see the full breakdown and can change the total. Nothing goes out until you say yes.</p>
            </div>
            <div className="flow-step">
              <span className="n">Step 3</span>
              <h3>The customer gets only the total</h3>
              <p>One message with the final price. The breakdown stays with you.</p>
            </div>
          </div>
          <div className="flow-stage" aria-hidden="true">
            <div className="stage-card">
              <div className="wa">
                <div className="msg">Hi, my kitchen sink is leaking.</div>
                <div className="msg me">Sorry to hear that. Is it dripping or running?</div>
                <div className="msg">Dripping under the sink since yesterday.</div>
                <div className="msg me">Thanks. Which area are you in, and when suits you?</div>
                <div className="msg">Subang Jaya, Saturday morning.</div>
              </div>
            </div>
            <div className="stage-card">
              <div className="sheet">
                {[
                  ["Labour", "140.00", 70],
                  ["Parts & materials", "118.00", 58],
                  ["Call-out", "60.00", 30],
                  ["Overheads & profit", "62.00", 32],
                ].map(([n, v, w]) => (
                  <div key={n as string}>
                    <div className="row">
                      <span>{n}</span>
                      <b className="num">{v}</b>
                    </div>
                    <div className="bar">
                      <i style={{ "--w": "100%", width: `${w}%` } as React.CSSProperties} />
                    </div>
                  </div>
                ))}
                <div className="row total">
                  <span>Total</span>
                  <span className="num">RM 380.00</span>
                </div>
                <div className="ask">
                  <span>Send this total to the customer?</span>
                  <b>Yes, send</b>
                </div>
              </div>
            </div>
            <div className="stage-card">
              <div className="final-bubble">
                Your price for the sink repair
                <strong className="num">RM 380.00</strong>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="cta">
        <h2>Link your WhatsApp.</h2>
        <div className="hero-actions">
          <Link to="/app" className="btn primary">
            Open dashboard
          </Link>
        </div>
        <div className="foot">
          <span>Gesir, your AI middleman for any trade</span>
          <span>Prices in MYR</span>
        </div>
      </section>
    </div>
  );
}

