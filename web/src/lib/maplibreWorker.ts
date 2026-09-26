// maplibre-gl 6 ships its tile worker as a separate module and locates it with
// `new URL(..., import.meta.url)`, which Vite's dependency pre-bundling breaks
// (dev: "Worker failed to load", blank maps). Point it at the worker file
// explicitly; Vite emits the file and resolves this URL in dev and build.
import { setWorkerUrl } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";

setWorkerUrl(workerUrl);
