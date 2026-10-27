// Entry for the intro sequence (intro.html). Like the pitch demo it is not
// wrapped in <StrictMode>: the preload builds one MapLibre instance and warms
// its tile cache, and a double mount would do that twice.
import { createRoot } from "react-dom/client";
// maplibre's stylesheet first, so the stage's full-bleed map rules win on order
import "maplibre-gl/dist/maplibre-gl.css";
import "./intro.css";
import Intro from "./Intro";

createRoot(document.getElementById("intro")!).render(<Intro />);
