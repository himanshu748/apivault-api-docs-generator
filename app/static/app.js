const state = {
  view: "docs",
  latestDocument: null,
  latestSource: "",
};

const elements = {
  sidebarTree: document.getElementById("sidebarTree"),
  sidebarStatus: document.getElementById("sidebarStatus"),
  refreshSidebarBtn: document.getElementById("refreshSidebarBtn"),
  setupBtn: document.getElementById("setupBtn"),
  docForm: document.getElementById("docForm"),
  documentEndpointBtn: document.getElementById("documentEndpointBtn"),
  documentCollectionBtn: document.getElementById("documentCollectionBtn"),
  generateReadmeBtn: document.getElementById("generateReadmeBtn"),
  previewHeading: document.getElementById("previewHeading"),
  flashMessage: document.getElementById("flashMessage"),
  docsOutput: document.getElementById("docsOutput"),
  emptyState: document.getElementById("emptyState"),
  docsView: document.getElementById("docsView"),
  sourceView: document.getElementById("sourceView"),
  sourceCode: document.getElementById("sourceCode"),
  searchInput: document.getElementById("searchInput"),
  searchResults: document.getElementById("searchResults"),
  codeInput: document.getElementById("codeInput"),
  languageInput: document.getElementById("languageInput"),
  serviceInput: document.getElementById("serviceInput"),
  baseUrlInput: document.getElementById("baseUrlInput"),
  toggleButtons: document.querySelectorAll(".toggle-button"),
};

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail || payload.message || "Request failed.";
    throw new Error(detail);
  }
  return payload;
}

function showMessage(message, tone = "warning") {
  elements.flashMessage.textContent = message;
  elements.flashMessage.classList.remove("hidden");
  elements.flashMessage.style.background =
    tone === "success" ? "rgba(123, 224, 195, 0.14)" : "rgba(255, 174, 87, 0.14)";
  elements.flashMessage.style.borderColor =
    tone === "success" ? "rgba(123, 224, 195, 0.22)" : "rgba(255, 174, 87, 0.22)";
  elements.flashMessage.style.color = tone === "success" ? "#c9ffe9" : "#ffd7ab";
}

function clearMessage() {
  elements.flashMessage.classList.add("hidden");
}

function escapeHtml(value = "") {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function syntaxHighlight(code = "") {
  let highlighted = escapeHtml(code);
  highlighted = highlighted.replace(
    /(#[^\n]*|\/\/[^\n]*)/g,
    '<span class="token-comment">$1</span>'
  );
  highlighted = highlighted.replace(
    /("(?:\\.|[^"])*"|'(?:\\.|[^'])*')/g,
    '<span class="token-string">$1</span>'
  );
  highlighted = highlighted.replace(
    /\b(\d+(?:\.\d+)?)\b/g,
    '<span class="token-number">$1</span>'
  );
  highlighted = highlighted.replace(
    /\b(async|await|def|return|class|const|let|var|function|if|else|for|while|try|except|raise|import|from|true|false|null)\b/gi,
    '<span class="token-keyword">$1</span>'
  );
  return highlighted;
}

function methodClass(method = "") {
  return `method-${method.toLowerCase()}`;
}

function renderSidebar(data) {
  const services = data.services || [];
  elements.sidebarStatus.textContent = services.length
    ? `Showing ${services.length} services from ${data.source || "cache"}.`
    : "No services found yet. Run setup, then document an endpoint.";

  elements.sidebarTree.innerHTML = services
    .map(
      (service) => `
        <section class="service-block">
          <div class="service-head">
            <strong>${escapeHtml(service.name)}</strong>
            <span>${escapeHtml(service.base_url || "")}</span>
          </div>
          <div class="endpoint-list">
            ${(service.endpoints || [])
              .map(
                (endpoint) => `
                  <article class="endpoint-item">
                    <h4><span class="method-badge ${methodClass(endpoint.method)}">${escapeHtml(
                      endpoint.method
                    )}</span> ${escapeHtml(endpoint.path)}</h4>
                    <p>${escapeHtml(endpoint.description || "")}</p>
                    ${
                      endpoint.notion_url
                        ? `<a href="${endpoint.notion_url}" target="_blank" rel="noreferrer">View in Notion →</a>`
                        : ""
                    }
                  </article>
                `
              )
              .join("")}
          </div>
        </section>
      `
    )
    .join("");
}

function renderSearchResults(payload) {
  const results = payload.results || [];
  if (!results.length && elements.searchInput.value.trim()) {
    elements.searchResults.innerHTML = `<div class="result-item"><p>No endpoints matched that query.</p></div>`;
    return;
  }
  elements.searchResults.innerHTML = results
    .map(
      (item) => `
        <article class="result-item">
          <h4><span class="method-badge ${methodClass(item.method)}">${escapeHtml(
            item.method
          )}</span> ${escapeHtml(item.path)} <span class="meta-pill">${escapeHtml(
            item.service
          )}</span></h4>
          <p>${escapeHtml(item.description)}</p>
          ${
            item.notion_url
              ? `<a href="${item.notion_url}" target="_blank" rel="noreferrer">View in Notion →</a>`
              : ""
          }
        </article>
      `
    )
    .join("");
}

function renderDocs(documentation) {
  if (!documentation) {
    elements.docsOutput.innerHTML = "";
    elements.emptyState.classList.remove("hidden");
    return;
  }

  elements.emptyState.classList.add("hidden");
  const parameters = documentation.request_parameters || [];
  const errors = documentation.error_codes || [];
  const assumptions = documentation.assumptions || [];

  elements.docsOutput.innerHTML = `
    <div class="docs-sheet">
      <section class="docs-head">
        <div class="pill-row">
          <span class="method-badge ${methodClass(documentation.method)}">${escapeHtml(
            documentation.method
          )}</span>
          <span class="meta-pill">${escapeHtml(documentation.service)}</span>
          <span class="meta-pill">${escapeHtml(documentation.version || "v1")}</span>
          <span class="meta-pill">${documentation.auth_required ? "Auth required" : "Public"}</span>
          <span class="meta-pill">${documentation.deprecated ? "Deprecated" : "Active"}</span>
        </div>
        <h4>${escapeHtml(documentation.title)}</h4>
        <p class="path-line"><code>${escapeHtml(
          `${documentation.base_url}${documentation.path}`
        )}</code></p>
        <p>${escapeHtml(documentation.description)}</p>
        ${
          documentation.notion_url
            ? `<p class="link-row"><a href="${documentation.notion_url}" target="_blank" rel="noreferrer">View in Notion →</a></p>`
            : ""
        }
      </section>

      <section class="doc-section">
        <h5>Summary</h5>
        <p>${escapeHtml(documentation.summary)}</p>
      </section>

      <section class="doc-section">
        <h5>Request Parameters</h5>
        ${
          parameters.length
            ? `
              <table class="doc-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Required</th>
                    <th>Location</th>
                    <th>Description</th>
                  </tr>
                </thead>
                <tbody>
                  ${parameters
                    .map(
                      (param) => `
                        <tr>
                          <td><code>${escapeHtml(param.name)}</code></td>
                          <td>${escapeHtml(param.type)}</td>
                          <td>${param.required ? "Yes" : "No"}</td>
                          <td>${escapeHtml(param.location || "query")}</td>
                          <td>${escapeHtml(param.description)}</td>
                        </tr>
                      `
                    )
                    .join("")}
                </tbody>
              </table>
            `
            : "<p>No explicit request parameters were inferred.</p>"
        }
      </section>

      ${renderSchemaSection("Request Body JSON Schema", documentation.request_body_schema)}
      ${renderSchemaSection("Request Body Example", documentation.request_body_example)}
      ${renderSchemaSection("Response Schema", documentation.response_schema)}
      ${renderSchemaSection("Response Example", documentation.response_example)}

      <section class="doc-section">
        <h5>Error Codes</h5>
        <table class="doc-table">
          <thead>
            <tr><th>Code</th><th>Meaning</th></tr>
          </thead>
          <tbody>
            ${errors
              .map(
                (item) => `
                  <tr>
                    <td><code>${escapeHtml(String(item.code))}</code></td>
                    <td>${escapeHtml(item.meaning)}</td>
                  </tr>
                `
              )
              .join("")}
          </tbody>
        </table>
      </section>

      ${renderCodeSection("curl", documentation.curl_example)}
      ${renderCodeSection("python", documentation.python_example)}
      ${renderCodeSection("javascript", documentation.javascript_example)}

      ${
        assumptions.length
          ? `
            <section class="doc-section">
              <h5>Assumptions</h5>
              <ul>
                ${assumptions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
              </ul>
            </section>
          `
          : ""
      }
    </div>
  `;
}

function renderSchemaSection(label, payload) {
  return `
    <section class="doc-section">
      <h5>${escapeHtml(label)}</h5>
      <pre class="code-panel"><code>${syntaxHighlight(
        JSON.stringify(payload ?? {}, null, 2)
      )}</code></pre>
    </section>
  `;
}

function renderCodeSection(language, source) {
  return `
    <section class="doc-section">
      <h5>${escapeHtml(language)} Example</h5>
      <pre class="code-panel"><code>${syntaxHighlight(source || "")}</code></pre>
    </section>
  `;
}

function setView(view) {
  state.view = view;
  elements.toggleButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === view);
  });
  elements.docsView.classList.toggle("hidden", view !== "docs");
  elements.sourceView.classList.toggle("hidden", view !== "source");
}

async function loadSidebar(fresh = false) {
  try {
    const payload = await fetchJSON(`/api/sidebar${fresh ? "?fresh=true" : ""}`);
    renderSidebar(payload);
  } catch (error) {
    elements.sidebarStatus.textContent = error.message;
    elements.sidebarTree.innerHTML = "";
  }
}

async function handleSetup() {
  clearMessage();
  showMessage("Running Notion workspace setup...");
  try {
    const payload = await fetchJSON("/api/setup", { method: "POST", body: "{}" });
    showMessage(
      `Setup complete. Hub: ${payload.hub_page_url || "created"} | ${payload.auth_notice}`,
      "success"
    );
    await loadSidebar(true);
  } catch (error) {
    showMessage(error.message);
  }
}

function formPayload() {
  return {
    code: elements.codeInput.value,
    language: elements.languageInput.value,
    service: elements.serviceInput.value,
    base_url: elements.baseUrlInput.value,
  };
}

async function handleDocument(endpointUrl) {
  clearMessage();
  const payload = formPayload();
  state.latestSource = payload.code;
  elements.previewHeading.textContent = "Generating documentation...";

  try {
    const response = await fetchJSON(endpointUrl, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (response.items) {
      const first = response.items[0];
      state.latestDocument = first ? first.documentation : null;
      showMessage(`Created ${response.count} documentation entries.`, "success");
      renderDocs(first ? first.documentation : null);
      elements.previewHeading.textContent = first
        ? `${first.method} ${first.path}`
        : "Collection documented";
    } else {
      state.latestDocument = response.documentation;
      showMessage(
        `Documented ${response.method} ${response.path}${response.notion_url ? " and stored it in Notion." : "."}`,
        "success"
      );
      renderDocs(response.documentation);
      elements.previewHeading.textContent = `${response.method} ${response.path}`;
    }

    elements.sourceCode.innerHTML = syntaxHighlight(state.latestSource);
    await loadSidebar(true);
    setView("docs");
  } catch (error) {
    showMessage(error.message);
    elements.previewHeading.textContent = "Generated docs will appear here";
  }
}

async function handleGenerateReadme() {
  clearMessage();
  const payload = { service: elements.serviceInput.value };
  try {
    const response = await fetchJSON("/api/generate-readme", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showMessage(
      `README created for ${response.service}${response.notion_url ? `: ${response.notion_url}` : "."}`,
      "success"
    );
  } catch (error) {
    showMessage(error.message);
  }
}

let searchTimer = null;
function scheduleSearch() {
  clearTimeout(searchTimer);
  const query = elements.searchInput.value.trim();
  if (!query) {
    elements.searchResults.innerHTML = "";
    return;
  }
  searchTimer = setTimeout(async () => {
    try {
      const payload = await fetchJSON(`/api/search?q=${encodeURIComponent(query)}`);
      renderSearchResults(payload);
    } catch (error) {
      elements.searchResults.innerHTML = `<div class="result-item"><p>${escapeHtml(
        error.message
      )}</p></div>`;
    }
  }, 220);
}

elements.toggleButtons.forEach((button) =>
  button.addEventListener("click", () => setView(button.dataset.view))
);
if (elements.documentEndpointBtn) {
  elements.documentEndpointBtn.addEventListener("click", () =>
    handleDocument("/api/document-endpoint")
  );
}
elements.refreshSidebarBtn.addEventListener("click", () => loadSidebar(true));
elements.setupBtn.addEventListener("click", handleSetup);
elements.docForm.addEventListener("submit", (event) => {
  event.preventDefault();
  handleDocument("/api/document-endpoint");
});
elements.documentCollectionBtn.addEventListener("click", () =>
  handleDocument("/api/document-collection")
);
elements.generateReadmeBtn.addEventListener("click", handleGenerateReadme);
elements.searchInput.addEventListener("input", scheduleSearch);

loadSidebar();
setView("docs");
