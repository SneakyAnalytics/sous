import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import CartReview from "./CartReview";
import ShoppingChecklist from "./ShoppingChecklist";

/** Picks the shopping experience the server is set up for: the checklist (default) or the automated cart review. */
export default function Shopping({ items, week, onClose }) {
  const { data } = useQuery({ queryKey: ["cart-mode"], queryFn: api.cartMode, staleTime: Infinity });
  if (!data) return null;
  return data.mode === "assist" ? <ShoppingChecklist items={items} week={week} onClose={onClose} /> : <CartReview items={items} onClose={onClose} />;
}
