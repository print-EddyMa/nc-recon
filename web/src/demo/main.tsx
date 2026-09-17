// Phase H - isolated entry for the scripted hook sequence. Deliberately NOT
// wrapped in <StrictMode>: the preload builds one MapLibre instance and warms
// its tile cache, and a double-mount would run that twice. This is a recording
// tool, not part of the interactive app.
import { createRoot } from "react-dom/client";
import "./demo.css";
import Demo from "./Demo";

createRoot(document.getElementById("demo")!).render(<Demo />);
