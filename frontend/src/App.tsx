import { BrowserRouter, Route, Routes } from "react-router-dom";
import { CampaignSetupPage } from "@/pages/CampaignSetupPage";
import { GamePage } from "@/pages/GamePage";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<CampaignSetupPage />} />
        <Route path="/game" element={<GamePage />} />
      </Routes>
    </BrowserRouter>
  );
}
