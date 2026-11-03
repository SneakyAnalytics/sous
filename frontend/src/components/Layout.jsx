import React, { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { BookOpen, CalendarDays, ChefHat, Heart, Moon, Sun } from "lucide-react";
import { applyTheme } from "../lib/theme";
import { brandBadge } from "../assets";

const NAV = [
  { to: "/", icon: ChefHat, label: "Chef", end: true },
  { to: "/recipes", icon: BookOpen, label: "Recipes" },
  { to: "/plan", icon: CalendarDays, label: "This Week" },
  { to: "/taste", icon: Heart, label: "Taste" },
];

export default function Layout() {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || "light");
  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    applyTheme(next);
    setTheme(next);
  };
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand"><img src={brandBadge} alt="" width="40" height="40" /> Sous</div>
        {NAV.map(({ to, icon: Icon, label, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
            <Icon size={22} /> <span>{label}</span>
          </NavLink>
        ))}
        <div className="spacer" />
        <button className="icon-btn" onClick={toggle} aria-label="Toggle dark mode">
          {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
        </button>
      </aside>
      <main className="main"><Outlet /></main>
    </div>
  );
}
