import React from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Chef from "./pages/Chef";
import Recipes from "./pages/Recipes";
import RecipeDetail from "./pages/RecipeDetail";
import Plan from "./pages/Plan";
import Cook from "./pages/Cook";
import Taste from "./pages/Taste";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Cook mode is full screen: no sidebar */}
        <Route path="/cook/:id" element={<Cook />} />
        <Route element={<Layout />}>
          <Route path="/" element={<Chef />} />
          <Route path="/recipes" element={<Recipes />} />
          <Route path="/recipes/:id" element={<RecipeDetail />} />
          <Route path="/plan" element={<Plan />} />
          <Route path="/taste" element={<Taste />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
