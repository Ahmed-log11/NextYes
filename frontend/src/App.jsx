import { Routes, Route } from "react-router-dom";
import Landing from "./pages/Landing.jsx";
import Business from "./pages/Business.jsx";
import Bank from "./pages/Bank.jsx";
import Results from "./pages/Results.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/business" element={<Business />} />
      <Route path="/bank" element={<Bank />} />
      <Route path="/results" element={<Results />} />
      <Route path="*" element={<Landing />} />
    </Routes>
  );
}
