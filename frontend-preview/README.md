# Agent Bazaar frontend preview

A static, design-only build of the Agent Bazaar interface. It combines the interface work from the `maria`, `rameen` and `qaim` branches and the supplied Figma screens.

- No backend is connected.
- Every API response is local mock data.
- All routes, filters, modals, theme states and simulated execution states work in the browser.
- This folder is self-contained. It can be opened from any location.

## Open in VS Code

1. Open VS Code.
2. Choose **File > Open Folder** and select this `frontend-preview` folder.
3. Open `index.html`.

### Option A: Live Server (recommended)

1. Open Extensions (`Ctrl+Shift+X`).
2. Search for `Live Server` by **Ritwick Dey**.
3. Click **Install**. VS Code may also show this as a recommended extension when the folder opens.
4. Right-click `index.html` in the Explorer and choose **Open with Live Server**.
5. The preview opens at:
   `http://127.0.0.1:5500/index.html`

### Option B: Python, no extension

1. Open the VS Code terminal (`Ctrl+``).
2. Run:

```powershell
python -m http.server 5510 --bind 127.0.0.1
```

3. Open:
   `http://127.0.0.1:5510/index.html`

You can also press `Ctrl+Shift+B` to run the included **Start frontend preview** VS Code task, which starts the same server.

Stop either server with `Ctrl+C` in its terminal.

## Pages

| File | Screen |
| --- | --- |
| `index.html` | Developer workspace / dashboard |
| `marketplace.html` | Service marketplace |
| `monitor.html` | Self-healing monitor |
| `library.html` | Interface library and component states |

The sidebar switches between files, so no server-side routing is required. The **Documentation** link opens the preview guide modal.

## Share with the team

1. Commit and push the `frontend-preview/` folder to a branch.
2. Teammates pull the branch, open the folder in VS Code, and use Live Server or Python as above.
3. For a live walkthrough, start **Live Share** in VS Code and share the local preview URL.

## Updating the preview

- Mock content: `assets/mock-data.js`
- Mock API handlers: `assets/mock-api.js`
- Preview-only routing and docs behavior: `assets/preview.js`
- Shared styles: `assets/styles.css`
- Shared interface behavior: `assets/app.js`

When the backend is ready, remove the `assets/mock-api.js` script tag and serve the same shell through FastAPI. The existing backend-wired UI lives in `app/web/` in the main repository.

## Design source

The preview follows the supplied Figma frames and the three branch implementations:

- `maria`: sourcing, free-first ranking, typed workbench, trace, monitoring, library and document flows.
- `rameen`: Figma-matched console shell, window cards, routes and interaction states.
- `qaim`: authority/claim labels, drift evidence, trust probes and breaker isolation.

The new Figma Make link currently requires a Figma login. Export the frames or make the file publicly viewable to compare it directly with this build.
