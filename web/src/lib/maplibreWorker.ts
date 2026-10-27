// maplibre-gl 6 ships its tile worker as a separate ES module that imports a
// sibling chunk (./maplibre-gl-shared.mjs) and locates it with
// `new URL(..., import.meta.url)`. Vite's pre-bundling breaks that in dev, and
// a plain `?url` import copies only the worker file (not its import) into the
// build. `?worker&url` makes Vite bundle the worker with its dependencies into
// one self-contained module and hand back its URL; maplibre starts it with
// `{ type: "module" }`.
import { setWorkerUrl } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

setWorkerUrl(workerUrl);
