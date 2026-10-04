const bugForm = document.getElementById("bugForm");
const analyzeButton = document.getElementById("analyzeButton");
const clearButton = document.getElementById("clearButton");
const diagnosisButton = document.getElementById("diagnosisButton");
const diagnosisModal = document.getElementById("diagnosisModal");
const diagnosisCloseButton = document.getElementById("diagnosisCloseButton");
const serviceDiagnosisMessage = document.getElementById("serviceDiagnosisMessage");
const diagnosisRetryButton = document.getElementById("diagnosisRetryButton");

const resultCard = document.getElementById("resultCard");
const resultGrid = document.getElementById("resultGrid");
const visualEvidenceSection = document.getElementById("visualEvidenceSection");
const visualEvidenceValue = document.getElementById("visualEvidenceValue");
const resultHeading = document.getElementById("resultHeading");
const exportButton = document.getElementById("exportButton");
const exportError = document.getElementById("exportError");

const errorCard = document.getElementById("errorCard");
const errorMessage = document.getElementById("errorMessage");

const themeSwitch = document.getElementById("themeSwitch");

const statusDot = document.getElementById("statusDot");
const serviceValue = document.getElementById("serviceValue");

const singleBugMode = document.getElementById("singleBugMode");
const batchAnalysisMode = document.getElementById("batchAnalysisMode");

const batchAnalysis = document.getElementById("batchAnalysis");
const batchFileInput = document.getElementById("batchFileInput");
const batchFileName = document.getElementById("batchFileName");
const batchClearButton = document.getElementById("batchClearButton");
const batchAnalyzeButton = document.getElementById("batchAnalyzeButton");

// Single bug and batch analysis share the result area but keep their
// own last result, so an analysis that finishes in the other mode
// never replaces what is on screen. Each entry is null,
// { type: "result", data } or { type: "error", message }.
let activeMode = "single";
const savedResults = { single: null, batch: null };

// Clear cancels a running analysis of its mode; the server notices
// the closed request and stops sending its bugs to Ollama.
let singleAbortController = null;
let batchAbortController = null;

// Same limit as MAX_EXCEL_BYTES in app/services/batch_analyzer.py.
const MAX_BATCH_FILE_BYTES = 5 * 1024 * 1024;

// Both analyze buttons follow the service status and whether an
// analysis of that kind is already running.
let serviceStatus = "checking";
let singleAnalysisRunning = false;
let batchAnalysisRunning = false;

// Shown on the analyze buttons while they cannot be used because of
// the service status.
const SERVICE_BUTTON_TOOLTIPS = {
    checking: "Analysis service checking. Please wait until the check is finished.",
    unavailable: "Analysis service unavailable. Open the ⚠ diagnosis next to the status for details."
};

function refreshAnalyzeButtons() {
    const serviceUsable = serviceStatus === "available";

    analyzeButton.disabled = !serviceUsable || singleAnalysisRunning;
    batchAnalyzeButton.disabled =
        !serviceUsable ||
        batchAnalysisRunning ||
        !batchFileInput.files[0] ||
        batchFileInput.files[0].size > MAX_BATCH_FILE_BYTES;

    const tooltip = SERVICE_BUTTON_TOOLTIPS[serviceStatus];
    for (const button of [analyzeButton, batchAnalyzeButton]) {
        const wrapper = button.parentElement;
        if (tooltip) {
            wrapper.setAttribute("data-tooltip", tooltip);
        } else {
            wrapper.removeAttribute("data-tooltip");
        }
    }

    const retryButton = document.getElementById("batchRetryButton");
    if (retryButton) {
        retryButton.disabled = !serviceUsable || batchAnalysisRunning;
    }
}

async function getAnalysisDiagnosisData() {
    try {
        const response = await fetch("/health/analysis/diagnose", {
            method: "GET",
            cache: "no-store"
        });

        let data;

        try {
            data = await response.json();
        } catch {
            data = null;
        }

        if (!response.ok || !data) {
            return null;
        }

        return data;

    } catch {
        return null;
    }
}

// Diagnosis messages are built as HTML, but their reasons can contain
// text from Ollama or the model, so they must never be rendered as HTML.
function escapeHtml(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function getAnalysisDiagnosis(data) {
    if (!data) {
        return `
            <div class="diagnosis-item">
                <div class="diagnosis-item-header">
                    <span class="diagnosis-status-dot unavailable"></span>
                    <span class="diagnosis-item-title">Diagnosis</span>
                    <span class="diagnosis-status-text unavailable">
                        Unavailable
                    </span>
                </div>

                <div class="diagnosis-item-message">
                    No diagnostic information was returned.
                </div>
            </div>
        `;
    }

    const items = [];

    /*
     * Application
     */

    const applicationStatus =
        data.application?.status || "unavailable";

    const applicationAvailable =
        applicationStatus === "available";

    items.push(`
        <div class="diagnosis-item">
            <div class="diagnosis-item-header">

                <span class="diagnosis-status-dot ${applicationAvailable
            ? "available"
            : "unavailable"
        }"></span>

                <span class="diagnosis-item-title">
                    Application
                </span>

                <span class="diagnosis-status-text ${applicationAvailable
            ? "available"
            : "unavailable"
        }">
                    ${applicationAvailable
            ? "Available"
            : "Unavailable"
        }
                </span>

            </div>

            <div class="diagnosis-item-message">
                ${escapeHtml(data.application?.reason ||
        "FastAPI application is running."
        )}
            </div>
        </div>
    `);


    /*
     * Ollama
     */

    const ollamaStatus =
        data.ollama?.status || "unavailable";

    const ollamaAvailable =
        ollamaStatus === "available";

    items.push(`
        <div class="diagnosis-item">

            <div class="diagnosis-item-header">

                <span class="diagnosis-status-dot ${ollamaAvailable
            ? "available"
            : "unavailable"
        }"></span>

                <span class="diagnosis-item-title">
                    Ollama
                </span>

                <span class="diagnosis-status-text ${ollamaAvailable
            ? "available"
            : "unavailable"
        }">
                    ${ollamaAvailable
            ? "Available"
            : "Unavailable"
        }
                </span>

            </div>

            ${data.ollama?.reason
            ? `
                    <div class="diagnosis-item-message">
                        ${escapeHtml(data.ollama.reason)}
                    </div>
                `
            : ""
        }

        </div>
    `);


    /*
     * Model
     */

    const modelStatus =
        data.model?.status ||
        data.model_status ||
        "not_checked";

    const modelClass =
        modelStatus === "available"
            ? "available"
            : modelStatus === "not_checked"
                ? "not-checked"
                : "unavailable";

    const modelLabel =
        modelStatus === "available"
            ? "Available"
            : modelStatus === "not_checked"
                ? "Not checked"
                : "Unavailable";

    items.push(`
        <div class="diagnosis-item">

            <div class="diagnosis-item-header">

                <span class="diagnosis-status-dot ${modelClass}">
                </span>

                <span class="diagnosis-item-title">
                    Model
                </span>

                <span class="diagnosis-status-text ${modelClass}">
                    ${modelLabel}
                </span>

            </div>

            <div class="diagnosis-item-message">
                Required model: qwen3-vl:8b-instruct
            </div>

            ${data.model?.reason
            ? `
                    <div class="diagnosis-item-message">
                        ${escapeHtml(data.model.reason)}
                    </div>
                `
            : ""
        }

        </div>
    `);


    /*
     * Inference
     */

    const inferenceStatus =
        data.inference?.status || "not_checked";

    const inferenceClass =
        inferenceStatus === "available"
            ? "available"
            : inferenceStatus === "not_checked"
                ? "not-checked"
                : "unavailable";

    const inferenceLabel =
        inferenceStatus === "available"
            ? "Available"
            : inferenceStatus === "not_checked"
                ? "Not checked"
                : "Unavailable";

    items.push(`
        <div class="diagnosis-item">

            <div class="diagnosis-item-header">

                <span class="diagnosis-status-dot ${inferenceClass}">
                </span>

                <span class="diagnosis-item-title">
                    Inference
                </span>

                <span class="diagnosis-status-text ${inferenceClass}">
                    ${inferenceLabel}
                </span>

            </div>

            ${data.inference?.reason
            ? `
                    <div class="diagnosis-item-message">
                        ${escapeHtml(data.inference.reason)}
                    </div>
                `
            : ""
        }

        </div>
    `);

    return items.join("");
}

singleBugMode.addEventListener("click", () => {
    singleBugMode.classList.add("active");
    batchAnalysisMode.classList.remove("active");

    bugForm.style.display = "";
    batchAnalysis.style.display = "none";
    activeMode = "single";
    displaySavedResult("single");
});

batchAnalysisMode.addEventListener("click", () => {
    batchAnalysisMode.classList.add("active");
    singleBugMode.classList.remove("active");

    bugForm.style.display = "none";
    batchAnalysis.style.display = "block";
    activeMode = "batch";
    displaySavedResult("batch");
});

function formatFileSize(bytes) {
    if (bytes < 1024 * 1024) {
        return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

batchFileInput.addEventListener("change", () => {
    const file = batchFileInput.files[0];
    const tooLarge = file && file.size > MAX_BATCH_FILE_BYTES;

    batchFileName.classList.toggle("invalid", Boolean(tooLarge));
    if (!file) {
        batchFileName.textContent = "No file chosen";
    } else if (tooLarge) {
        batchFileName.textContent =
            `${file.name} (${formatFileSize(file.size)}) is larger than the 5 MB limit.`;
    } else {
        batchFileName.textContent = `${file.name} (${formatFileSize(file.size)})`;
    }
    refreshAnalyzeButtons();
});

/*
 * Drag and drop
 */

const batchUploadBox = document.getElementById("batchUploadBox");
const BATCH_FILE_EXTENSIONS = [".xlsx", ".xls", ".csv"];

function isFileDrag(event) {
    return Array.from(event.dataTransfer?.types || []).includes("Files");
}

// A file dropped anywhere else would make the browser open it and
// leave the page, losing the results.
["dragover", "drop"].forEach(type => {
    window.addEventListener(type, event => {
        if (isFileDrag(event)) {
            event.preventDefault();
        }
    });
});

["dragenter", "dragover"].forEach(type => {
    batchUploadBox.addEventListener(type, event => {
        if (!isFileDrag(event)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
        batchUploadBox.classList.add("drag-over");
    });
});

batchUploadBox.addEventListener("dragleave", event => {
    // Moving over a child element also fires dragleave on the box.
    if (!batchUploadBox.contains(event.relatedTarget)) {
        batchUploadBox.classList.remove("drag-over");
    }
});

batchUploadBox.addEventListener("drop", event => {
    if (!isFileDrag(event)) return;
    event.preventDefault();
    batchUploadBox.classList.remove("drag-over");

    const file = event.dataTransfer.files[0];
    if (!file) return;

    const name = file.name.toLowerCase();
    if (!BATCH_FILE_EXTENSIONS.some(extension => name.endsWith(extension))) {
        batchFileInput.value = "";
        refreshAnalyzeButtons();
        batchFileName.textContent =
            `${file.name} is not supported. Drop an .xlsx, .xls or .csv file.`;
        batchFileName.classList.add("invalid");
        return;
    }

    // Only one file is analyzed; the first one is used.
    const selection = new DataTransfer();
    selection.items.add(file);
    batchFileInput.files = selection.files;
    batchFileInput.dispatchEvent(new Event("change"));
});

batchClearButton.addEventListener("click", () => {
    if (batchAbortController) {
        batchAbortController.abort();
    }
    stopBatchProgressPolling();
    stopBatchTimer();
    stopAnalyzingDots();
    document.getElementById("batchProgress").hidden = true;

    batchFileInput.value = "";
    batchFileName.textContent = "No file chosen";
    batchFileName.classList.remove("invalid");
    refreshAnalyzeButtons();
    currentBatchData = null;
    setSavedResult("batch", null);
});

let batchStartTime = null;
let batchTimerInterval = null;

function formatElapsedTime(seconds) {
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;

    return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function startBatchTimer() {
    batchStartTime = Date.now();

    const updateTimer = () => {
        const elapsedSeconds = Math.floor(
            (Date.now() - batchStartTime) / 1000
        );

        const timerElement = document.getElementById("batchProgressTime");

        if (timerElement) {
            timerElement.textContent =
                `⏱ ${formatElapsedTime(elapsedSeconds)}`;
        }
    };

    updateTimer();

    batchTimerInterval = setInterval(updateTimer, 1000);
}

function stopBatchTimer() {
    if (batchTimerInterval) {
        clearInterval(batchTimerInterval);
        batchTimerInterval = null;
    }
}

let analyzingDotsInterval = null;

function startAnalyzingDots() {
    if (analyzingDotsInterval) {
        return;
    }

    const progressStatus = document.getElementById("batchProgressStatus");

    let dots = 0;

    analyzingDotsInterval = setInterval(() => {
        dots = (dots + 1) % 4;
        progressStatus.textContent = "Analyzing" + ".".repeat(dots);
    }, 500);
}

function stopAnalyzingDots() {
    if (analyzingDotsInterval) {
        clearInterval(analyzingDotsInterval);
        analyzingDotsInterval = null;
    }
}

let batchProgressInterval = null;

// Results only live in this page, so leaving it while an analysis
// runs loses them; the browser asks the user to confirm first.
let runningAnalyses = 0;

window.addEventListener("beforeunload", event => {
    if (runningAnalyses > 0) {
        event.preventDefault();
        event.returnValue = "";
    }
});

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

function renderBatchProgress({ processed, total, done }) {
    const progressBox = document.getElementById("batchProgress");
    const progressCount = document.getElementById("batchProgressCount");
    const progressStatus = document.getElementById("batchProgressStatus");
    const progressFill = document.getElementById("batchProgressFill");

    const progressPercentage = document.getElementById(
        "batchProgressPercentage"
    );

    progressBox.hidden = false;

    progressCount.textContent = `${processed} / ${total} bugs processed`;

    if (done) {
        progressStatus.textContent = "Completed";
        progressStatus.classList.add("completed");
        stopBatchTimer();
        stopAnalyzingDots();
    } else {
        progressStatus.classList.remove("completed");
        startAnalyzingDots();
    }

    const percentage = total > 0 ? (processed / total) * 100 : 0;

    progressFill.style.width = `${percentage}%`;

    progressPercentage.textContent =
        `${Math.round(percentage)}%`;
}

// Each batch gets its own id so tabs running batches at the same
// time only see their own progress.
function createBatchId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
        return window.crypto.randomUUID();
    }

    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

async function fetchBatchProgress(batchId) {
    const response = await fetch(
        `/bugs/batch/${encodeURIComponent(batchId)}/progress`
    );

    // The batch is not registered yet (upload still running) or
    // has already finished.
    if (!response.ok) {
        return null;
    }

    return response.json();
}

// Rows rejected while reading the Excel file finish instantly, so they
// are left out of the live progress and animated in at the end.
function liveProcessedCount(progress) {
    return (
        progress.completed +
        progress.failed -
        (progress.rejected || 0) +
        (progress.not_analyzed || 0)
    );
}

function stopBatchProgressPolling() {
    if (batchProgressInterval) {
        clearInterval(batchProgressInterval);
        batchProgressInterval = null;
    }
}

function startBatchProgressPolling(batchId) {
    stopBatchProgressPolling();

    batchProgressInterval = setInterval(async () => {
        try {
            const progress = await fetchBatchProgress(batchId);

            // Polling was stopped (for example by Clear) meanwhile.
            if (!batchProgressInterval) {
                return;
            }

            if (!progress || progress.status !== "processing") {
                return;
            }

            renderBatchProgress({
                processed: liveProcessedCount(progress),
                total: progress.total,
                done: false
            });
        } catch (error) {
            console.error("Progress update failed:", error);
            stopBatchProgressPolling();
        }
    }, 1000);
}

// Stops early when the batch is cleared during the animation.
async function finishBatchProgress(data, signal) {
    stopBatchProgressPolling();

    const total = data.total;
    let processed = total - (data.rejected || 0) - (data.duplicates || 0);

    const remaining = total - processed;
    const stepDelay = Math.min(1750, 15000 / Math.max(remaining, 1));

    for (; processed < total; processed += 1) {
        renderBatchProgress({ processed, total, done: false });
        await sleep(stepDelay);
        if (signal.aborted) {
            return;
        }
    }

    renderBatchProgress({ processed: total, total, done: true });
}

// Result of the last batch; a retry updates it in place.
let currentBatchData = null;

// Sends only the bugs that were not analyzed because Ollama stopped,
// using the values from the last result, and merges the new results
// into it by Excel row.
// Bugs worth sending again: not analyzed because Ollama stopped, or
// failed because of the LLM (an unusable answer). Rows rejected while
// reading the file or judged not to be bug reports fail again.
function isRetryableBug(bug) {
    return (
        bug.status === "not_analyzed" ||
        (bug.status === "failed" && (bug.error || "").startsWith(LLM_ERROR_PREFIX))
    );
}

async function retryNotAnalyzedBugs() {
    const data = currentBatchData;
    const bugsToRetry = data ? data.bugs.filter(isRetryableBug) : [];

    if (!bugsToRetry.length) {
        return;
    }

    const batchId = createBatchId();
    const retryButton = document.getElementById("batchRetryButton");
    const abortController = new AbortController();
    batchAbortController = abortController;

    batchAnalysisRunning = true;
    refreshAnalyzeButtons();
    runningAnalyses += 1;
    retryButton.textContent = "Retrying...";

    startBatchTimer();
    startBatchProgressPolling(batchId);

    try {
        const response = await fetch("/bugs/batch/retry", {
            method: "POST",
            signal: abortController.signal,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                batch_id: batchId,
                bugs: bugsToRetry.map(bug => ({ row: bug.row, bug: bug.bug }))
            })
        });
        const retryData = await response.json();

        if (!response.ok) {
            throw retryData;
        }

        await finishBatchProgress(retryData, abortController.signal);
        if (abortController.signal.aborted) {
            return;
        }

        const retriedByRow = new Map(retryData.bugs.map(bug => [bug.row, bug]));
        currentBatchData = {
            ...data,
            stopped_reason: retryData.stopped_reason,
            retry_error: null,
            bugs: data.bugs.map(bug => retriedByRow.get(bug.row) || bug)
        };

        setSavedResult("batch", { type: "result", data: currentBatchData });
        document.getElementById("batchProgress").hidden = false;

        if (retryData.bugs.some(bug => (bug.error || "").startsWith(LLM_ERROR_PREFIX))) {
            checkServiceStatus();
        }
    } catch (error) {
        if (abortController.signal.aborted) {
            return;
        }
        stopBatchProgressPolling();
        stopBatchTimer();
        stopAnalyzingDots();

        currentBatchData = { ...data, retry_error: formatError(error) };
        setSavedResult("batch", { type: "result", data: currentBatchData });
    } finally {
        if (batchAbortController === abortController) {
            batchAbortController = null;
        }
        runningAnalyses -= 1;
        batchAnalysisRunning = false;

        const button = document.getElementById("batchRetryButton");
        if (button) {
            button.textContent = button.dataset.label;
        }
        refreshAnalyzeButtons();
    }
}

batchAnalyzeButton.addEventListener("click", async () => {
    if (!batchFileInput.files[0]) return;

    if (!(await confirmStartWhileOtherRuns("batch", batchAnalyzeButton))) {
        return;
    }

    // The file may have been cleared while the warning was open.
    const file = batchFileInput.files[0];
    if (!file) return;

    const batchId = createBatchId();
    const abortController = new AbortController();
    batchAbortController = abortController;

    currentBatchData = null;
    setSavedResult("batch", null);
    document.getElementById("batchProgress").hidden = true;
    startBatchTimer();
    startBatchProgressPolling(batchId);

    batchAnalysisRunning = true;
    refreshAnalyzeButtons();
    runningAnalyses += 1;
    batchAnalyzeButton.innerHTML = `
                <span class="loading"><span class="spinner"></span>Analyzing Bugs</span>
            `;

    try {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("batch_id", batchId);
        const response = await fetch("/bugs/batch", {
            method: "POST",
            body: formData,
            signal: abortController.signal
        });
        let data;
        try {
            data = await response.json();
        } catch {
            data = await response.text();
        }
        if (!response.ok) throw data;
        await finishBatchProgress(data, abortController.signal);
        if (abortController.signal.aborted) {
            return;
        }
        // The file name is used for the Excel report.
        currentBatchData = { ...data, source_name: file.name };
        setSavedResult("batch", { type: "result", data: currentBatchData });
        document.getElementById("batchProgress").hidden = false;

        // Bugs that failed because of Ollama may mean the service went
        // down; refresh the status shown at the top.
        if (data.bugs.some(bug => (bug.error || "").startsWith(LLM_ERROR_PREFIX))) {
            checkServiceStatus();
        }
    } catch (error) {
        if (abortController.signal.aborted) {
            return;
        }
        stopBatchProgressPolling();
        stopBatchTimer();
        stopAnalyzingDots();
        document.getElementById("batchProgress").hidden = true;
        setSavedResult("batch", { type: "error", message: formatError(error) });
    } finally {
        if (batchAbortController === abortController) {
            batchAbortController = null;
        }
        runningAnalyses -= 1;
        batchAnalysisRunning = false;
        refreshAnalyzeButtons();
        batchAnalyzeButton.textContent = "Analyze Bugs";
    }
});

/* =========================
    Screenshot Upload
========================== */

const screenshotInput = document.getElementById("screenshot");
const screenshotFileName = document.getElementById("screenshot-file-name");

const screenshotButton = document.querySelector(".screenshot-button");
const screenshotCount = document.getElementById("screenshotCount");
const screenshotNotice = document.getElementById("screenshotNotice");

// Same limits as MAX_SCREENSHOTS and MAX_SCREENSHOT_BYTES in
// app/api/bugs.py.
const MAX_SCREENSHOTS = 5;
const MAX_SCREENSHOT_BYTES = 10 * 1024 * 1024;

let selectedScreenshots = [];

function showScreenshotNotice(messages) {
    screenshotNotice.textContent = messages.join(" ");
    screenshotNotice.hidden = messages.length === 0;
}

screenshotInput.addEventListener("change", () => {
    const messages = [];
    let skippedForCount = 0;

    Array.from(screenshotInput.files).forEach(file => {
        if (file.size > MAX_SCREENSHOT_BYTES) {
            messages.push(
                `${file.name} (${formatFileSize(file.size)}) is larger than 10 MB.`
            );
        } else if (selectedScreenshots.length >= MAX_SCREENSHOTS) {
            skippedForCount += 1;
        } else {
            selectedScreenshots.push(file);
        }
    });

    if (skippedForCount) {
        messages.push(
            `At most ${MAX_SCREENSHOTS} screenshots can be added; ` +
            `${skippedForCount} ${skippedForCount === 1 ? "was" : "were"} not added.`
        );
    }

    renderScreenshots();
    showScreenshotNotice(messages);

    screenshotInput.value = "";
});

function renderScreenshots() {
    screenshotFileName.innerHTML = "";

    const full = selectedScreenshots.length >= MAX_SCREENSHOTS;
    screenshotCount.textContent = `${selectedScreenshots.length}/${MAX_SCREENSHOTS}`;
    screenshotInput.disabled = full;
    screenshotButton.classList.toggle("disabled", full);

    if (selectedScreenshots.length === 0) {
        screenshotFileName.textContent = "No file chosen";
        return;
    }

    const list = document.createElement("div");
    list.className = "screenshot-list";

    selectedScreenshots.forEach((file, index) => {
        const item = document.createElement("div");
        item.className = "screenshot-item";

        const img = document.createElement("img");
        img.src = URL.createObjectURL(file);
        img.alt = file.name;

        const removeButton = document.createElement("button");
        removeButton.type = "button";
        removeButton.className = "screenshot-remove";
        removeButton.textContent = "×";

        removeButton.addEventListener("click", () => {
            selectedScreenshots.splice(index, 1);
            renderScreenshots();
            showScreenshotNotice([]);
        });

        item.appendChild(img);
        item.appendChild(removeButton);
        list.appendChild(item);
    });

    screenshotFileName.appendChild(list);
}

/*
 * Theme
 */

function updateThemeButton() {
    const isLight = document.body.classList.contains("light");

    themeSwitch.setAttribute(
        "aria-label",
        isLight
            ? "Switch to dark mode"
            : "Switch to light mode"
    );
}

// Browsers that block site data throw on any storage access; the
// theme is then simply not remembered.
function readSavedTheme() {
    try {
        return localStorage.getItem("ai-bug-analyzer-theme");
    } catch {
        return null;
    }
}

function saveTheme(theme) {
    try {
        localStorage.setItem("ai-bug-analyzer-theme", theme);
    } catch {
        // Not remembered; the switch still works for this page.
    }
}

function loadTheme() {
    const savedTheme = readSavedTheme();

    if (savedTheme === "light") {
        document.body.classList.add("light");
    } else {
        document.body.classList.remove("light");
    }

    updateThemeButton();
}

themeSwitch.addEventListener("click", () => {
    document.body.classList.toggle("light");

    const isLight = document.body.classList.contains("light");

    saveTheme(isLight ? "light" : "dark");

    updateThemeButton();
});

loadTheme();

/*
 * Validation
 */

const fields = {
    bugTitle: {
        input: document.getElementById("bugTitle"),
        error: document.getElementById("bugTitleError")
    },
    description: {
        input: document.getElementById("description"),
        error: document.getElementById("descriptionError")
    },
    stepsToReproduce: {
        input: document.getElementById("stepsToReproduce"),
        error: document.getElementById("stepsToReproduceError")
    },
    expectedResult: {
        input: document.getElementById("expectedResult"),
        error: document.getElementById("expectedResultError")
    },
    actualResult: {
        input: document.getElementById("actualResult"),
        error: document.getElementById("actualResultError")
    }
};

function clearValidation() {
    Object.values(fields).forEach(field => {
        field.input.classList.remove("invalid");
        field.error.classList.remove("visible");
    });
}

function validateForm() {
    clearValidation();

    let valid = true;

    Object.values(fields).forEach(field => {
        if (!field.input.value.trim()) {
            field.input.classList.add("invalid");
            field.error.classList.add("visible");
            valid = false;
        }
    });

    return valid;
}

Object.values(fields).forEach(field => {
    field.input.addEventListener("input", () => {
        if (field.input.value.trim()) {
            field.input.classList.remove("invalid");
            field.error.classList.remove("visible");
        }
    });
});

/*
 * Steps to reproduce
 *
 * IMPORTANT:
 * FastAPI expects steps_to_reproduce to be a LIST.
 *
 * The textarea contains:
 *
 * 1. Open the application
 * 2. Navigate to the upload screen
 * 3. Select an image
 *
 * This function converts it to:
 *
 * [
 *   "Open the application",
 *   "Navigate to the upload screen",
 *   "Select an image"
 * ]
 */

/*
 * Error formatting
 */

function formatError(error) {
    if (error === null || error === undefined) {
        return "Unknown error.";
    }

    if (typeof error === "string") {
        return error;
    }

    if (Array.isArray(error)) {
        return error
            .map(item => formatError(item))
            .join("\n");
    }

    // fetch() rejects with a TypeError when the server cannot be
    // reached; its properties are not enumerable, so it would show
    // as "{}".
    if (error instanceof TypeError) {
        return "Could not reach the analysis server. Make sure the app is still running and try again.";
    }

    if (error instanceof Error) {
        return error.message || String(error);
    }

    if (typeof error === "object") {
        // FastAPI errors: {"detail": "..."} or a list of
        // {"loc": ["body", "title"], "msg": "Field required"}
        if ("detail" in error) {
            return formatError(error.detail);
        }

        if (typeof error.msg === "string") {
            const field = (error.loc || [])
                .filter(part => !["body", "query", "path"].includes(part))
                .join(".")
                .replace(/_/g, " ");

            return field ? `${field}: ${error.msg}` : error.msg;
        }

        try {
            return JSON.stringify(error, null, 2);
        } catch {
            return String(error);
        }
    }

    return String(error);
}

function formatAnalysisValue(key, value) {
    if (key === "missing_information" && Array.isArray(value) && value.length === 0) {
        return "No missing information identified.";
    }

    return formatError(value) || "—";
}

/*
 * Result rendering
 */

function clearResults() {
    resultCard.classList.remove("visible");
    resultGrid.innerHTML = "";
    resultHeading.textContent = "Analysis Result";
    exportButton.hidden = true;
    exportError.hidden = true;

    visualEvidenceSection.hidden = true;
    visualEvidenceValue.textContent = "";

    errorCard.classList.remove("visible");
    errorMessage.textContent = "";
}

function showError(message) {
    clearResults();
    errorMessage.textContent = message;
    errorCard.classList.add("visible");
}

// Shows the saved result of a mode in the shared result area.
function displaySavedResult(mode) {
    const saved = savedResults[mode];

    if (!saved) {
        clearResults();
    } else if (saved.type === "error") {
        showError(saved.message);
    } else if (mode === "single") {
        renderAnalysis(saved.data);
    } else {
        renderBatchResults(saved.data);
    }

    // Only a rendered result can be exported, not an error.
    exportButton.hidden = !resultCard.classList.contains("visible");
}

// Keeps the result of a finished analysis and shows it only when its
// mode is on screen.
function setSavedResult(mode, result) {
    savedResults[mode] = result;

    if (activeMode === mode) {
        displaySavedResult(mode);
    }
}

function renderAnalysis(data) {
    clearResults();

    if (!data || typeof data !== "object") {
        showError("The analysis response was empty.");
        return;
    }

    /*
     * Some backend implementations return:
     *
     * {
     *   analysis: {...}
     * }
     *
     * while others return the analysis object directly.
     */

    const analysis =
        data.analysis &&
            typeof data.analysis === "object"
            ? data.analysis
            : data;

    const entries = Object.entries(analysis).filter(
        ([key]) =>
            key !== "confidence" &&
            key !== "visual_evidence" &&
            key !== "suggested_test_scenarios"
    );

    const confidence = analysis.confidence;
    const visualEvidence = analysis.visual_evidence;

    if (confidence !== undefined && confidence !== null) {
        const confidenceBadge = document.createElement("span");
        confidenceBadge.className = "confidence-badge";

        const confidenceValue =
            typeof confidence === "number"
                ? `${Math.round(confidence * 100)}%`
                : confidence;

        confidenceBadge.textContent = `Confidence: ${confidenceValue}`;

        confidenceBadge.setAttribute(
            "data-tooltip",
            "Indicates how confident the analysis is based on the information provided in the bug report. Higher confidence means the available information provides stronger support for the analysis."
        );
        confidenceBadge.setAttribute(
            "aria-label",
            "Indicates how confident the analysis is based on the information provided in the bug report. Higher confidence means the available information provides stronger support for the analysis."
        );

        resultHeading.appendChild(confidenceBadge);
    }

    if (!entries.length) {
        showError("The analysis response was empty.");
        return;
    }

    entries.forEach(([key, value]) => {
        const item = document.createElement("div");
        item.className = "result-item";

        const label = document.createElement("div");
        label.className = "result-label";

        const labelText = document.createElement("span");
        labelText.textContent = key.replace(/_/g, " ");

        label.appendChild(labelText);

        const tooltipTexts = {
            severity:
                "How much impact the bug has on the system or user experience. Critical issues may block a major function or make the application unusable.",

            priority:
                "How urgently the bug should be fixed from a product and business perspective. Higher priority means the issue should be addressed sooner.",

            category:
                "The type of problem identified in the bug report. Examples include Functional, UI, Performance, Security, Compatibility, and Data.",

            impact:
                "Describes how the bug affects users, business operations, system functionality, or the overall user experience.",

            possible_root_cause:
                "A likely technical or logical reason behind the observed bug. This is an analysis hypothesis and may require further investigation.",

            missing_information:
                "Important details that are missing from the bug report and could help QA investigate, reproduce, or validate the issue more effectively.",
        };

        const tooltipText = tooltipTexts[key];

        if (tooltipText) {
            const info = document.createElement("span");

            info.className = "info-tooltip";
            info.textContent = "i";
            info.setAttribute("data-tooltip", tooltipText);
            info.setAttribute("aria-label", tooltipText);

            label.appendChild(info);
        }

        const valueElement = document.createElement("div");
        valueElement.className = "result-value";

        valueElement.textContent = formatAnalysisValue(key, value);

        item.appendChild(label);
        item.appendChild(valueElement);

        resultGrid.appendChild(item);
    });

    const suggestedScenarios = analysis.suggested_test_scenarios;

    if (Array.isArray(suggestedScenarios) && suggestedScenarios.length) {
        const scenariosCard = document.createElement("div");
        scenariosCard.className = "suggested-scenarios-card";

        // Accordion header
        const accordionHeader = document.createElement("div");
        accordionHeader.className = "suggested-scenarios-header";

        const headerLeft = document.createElement("div");
        headerLeft.className = "suggested-scenarios-header-left";

        const arrow = document.createElement("span");
        arrow.className = "suggested-scenarios-arrow";
        arrow.textContent = "›";

        const labelText = document.createElement("span");
        labelText.textContent = "Suggested Test Scenarios";

        const info = document.createElement("span");
        info.className = "info-tooltip";
        info.textContent = "i";

        const tooltipText =
            "AI-generated test scenarios designed to validate the reported bug and verify the expected behavior after the fix. Each scenario includes the test case, expected result, purpose, category, and priority.";

        info.setAttribute("data-tooltip", tooltipText);
        info.setAttribute("aria-label", tooltipText);

        headerLeft.appendChild(arrow);
        headerLeft.appendChild(labelText);
        headerLeft.appendChild(info);

        accordionHeader.appendChild(headerLeft);

        // Accordion content
        const scenarios = document.createElement("div");
        scenarios.className = "test-scenarios";
        scenarios.hidden = true;

        suggestedScenarios.forEach((testCase) => {
            const scenario = document.createElement("div");
            scenario.className = "test-scenario";

            const header = document.createElement("div");
            header.className = "test-scenario-header";

            const id = document.createElement("span");
            id.className = "test-case-id";
            id.textContent = testCase.test_case_id || "Test Case";

            const meta = document.createElement("div");
            meta.className = "test-case-meta";
            meta.textContent = testCase.category || "QA Validation";

            const priority = document.createElement("span");
            priority.className =
                `test-case-priority ${(testCase.priority || "Medium").toLowerCase()}`;
            priority.textContent = testCase.priority || "Medium";

            header.appendChild(id);
            header.appendChild(meta);
            header.appendChild(priority);

            const scenarioSection = document.createElement("div");
            scenarioSection.className = "test-case-section";

            const scenarioLabel = document.createElement("div");
            scenarioLabel.className = "test-case-section-label";
            scenarioLabel.textContent = "Scenario";

            const scenarioText = document.createElement("div");
            scenarioText.className = "test-case-section-text";
            scenarioText.textContent = testCase.scenario || "";

            scenarioSection.appendChild(scenarioLabel);
            scenarioSection.appendChild(scenarioText);

            const expectedSection = document.createElement("div");
            expectedSection.className = "test-case-section";

            const expectedLabel = document.createElement("div");
            expectedLabel.className = "test-case-section-label";
            expectedLabel.textContent = "Expected Result";

            const expectedText = document.createElement("div");
            expectedText.className = "test-case-section-text";
            expectedText.textContent = testCase.expected_result || "";

            expectedSection.appendChild(expectedLabel);
            expectedSection.appendChild(expectedText);

            const purposeSection = document.createElement("div");
            purposeSection.className = "test-case-section";

            const purposeLabel = document.createElement("div");
            purposeLabel.className = "test-case-section-label";
            purposeLabel.textContent = "Purpose";

            const purposeText = document.createElement("div");
            purposeText.className = "test-case-section-text";
            purposeText.textContent = testCase.purpose || "";

            purposeSection.appendChild(purposeLabel);
            purposeSection.appendChild(purposeText);

            scenario.appendChild(header);
            scenario.appendChild(scenarioSection);
            scenario.appendChild(expectedSection);
            scenario.appendChild(purposeSection);

            scenarios.appendChild(scenario);
        });

        scenariosCard.appendChild(accordionHeader);
        scenariosCard.appendChild(scenarios);

        // Closed by default
        accordionHeader.addEventListener("click", () => {
            scenarios.hidden = !scenarios.hidden;
            scenariosCard.classList.toggle("is-open", !scenarios.hidden);
        });

        // IMPORTANT:
        // Keep Suggested Test Scenarios inside the current bug card
        resultGrid.appendChild(scenariosCard);
    }

    if (
        visualEvidence !== null &&
        visualEvidence !== undefined &&
        String(visualEvidence).trim()
    ) {
        visualEvidenceValue.textContent = visualEvidence;
        visualEvidenceSection.hidden = false;
    }

    resultCard.classList.add("visible");
}

function renderBatchResults(data) {
    clearResults();
    if (!data || !Array.isArray(data.bugs) || data.bugs.length === 0) {
        showError("The file did not contain any bug records.");
        return;
    }

    resultHeading.textContent = `Batch Analysis Result`;

    const llmFailedCount = data.bugs.filter(
        bug => bug.status === "failed" && isRetryableBug(bug)
    ).length;

    // Shown when Ollama stopped the batch, or when bugs failed only
    // because of an unusable LLM answer and can be sent again.
    if (data.stopped_reason || llmFailedCount) {
        const notice = document.createElement("div");
        notice.className = "result-item batch-stopped-notice";
        notice.setAttribute("role", "alert");

        const noticeLabel = document.createElement("div");
        noticeLabel.className = "result-label";
        noticeLabel.textContent = data.stopped_reason
            ? "Batch stopped"
            : "Some bugs could not be analyzed";

        const noticeText = document.createElement("div");
        noticeText.className = "result-value";
        if (data.retry_error) {
            noticeText.textContent = `Retry failed: ${data.retry_error}`;
        } else if (data.stopped_reason) {
            noticeText.textContent =
                `${data.stopped_reason} The remaining bugs were not analyzed.`;
        } else {
            noticeText.textContent =
                `${llmFailedCount} ${llmFailedCount === 1 ? "bug" : "bugs"} failed because the LLM returned an unusable answer. ${llmFailedCount === 1 ? "It" : "They"} can be analyzed again.`;
        }

        notice.append(noticeLabel, noticeText);

        if (data.bugs.some(isRetryableBug)) {
            const retryButton = document.createElement("button");
            retryButton.id = "batchRetryButton";
            retryButton.type = "button";
            retryButton.className = "batch-retry-button";
            retryButton.dataset.label = !data.stopped_reason
                ? "Retry failed bugs"
                : llmFailedCount
                    ? "Retry not analyzed and failed bugs"
                    : "Retry not analyzed bugs";
            retryButton.textContent = retryButton.dataset.label;
            retryButton.addEventListener("click", retryNotAnalyzedBugs);
            notice.appendChild(retryButton);
        }

        resultGrid.appendChild(notice);
        refreshAnalyzeButtons();
    }

    if (data.skipped_hidden_rows) {
        const hiddenInfo = document.createElement("div");
        hiddenInfo.className = "result-item batch-columns-info";

        const hiddenLabel = document.createElement("div");
        hiddenLabel.className = "result-label";
        hiddenLabel.textContent = "Hidden rows skipped";

        const hiddenText = document.createElement("div");
        hiddenText.className = "result-value";
        hiddenText.textContent =
            `${data.skipped_hidden_rows} hidden or filtered rows were not analyzed. Unhide them in Excel to include them.`;

        hiddenInfo.append(hiddenLabel, hiddenText);
        resultGrid.appendChild(hiddenInfo);
    }

    // Shown when the Excel headers were not recognized and the LLM
    // matched them, so the user can check the matching.
    if (data.detected_columns) {
        const fieldLabels = {
            title: "Title",
            description: "Description",
            steps_to_reproduce: "Steps to Reproduce",
            expected_result: "Expected Result",
            actual_result: "Actual Result",
            severity: "Severity",
            priority: "Priority",
            category: "Category"
        };

        const columnsInfo = document.createElement("div");
        columnsInfo.className = "result-item batch-columns-info";

        const columnsLabel = document.createElement("div");
        columnsLabel.className = "result-label";
        columnsLabel.textContent = "Columns detected automatically";

        const columnsText = document.createElement("div");
        columnsText.className = "result-value";
        columnsText.textContent = Object.entries(fieldLabels)
            .filter(([field]) => data.detected_columns[field])
            .map(([field, label]) => `${data.detected_columns[field]} → ${label}`)
            .join(" · ");

        columnsInfo.append(columnsLabel, columnsText);
        resultGrid.appendChild(columnsInfo);
    }
    const labels = {
        confidence: "Confidence",
        priority: "Priority",
        category: "Category",
        impact: "Impact",
        possible_root_cause: "Possible Root Cause",
        missing_information: "Missing Information"
    };

    const isDuplicateBug = bug => bug.status === "duplicate";

    // Not analyzed because Ollama stopped during the batch; the report
    // itself has no problem, unlike failed bugs.
    const isNotAnalyzedBug = bug => bug.status === "not_analyzed";

    const isFailedBug = bug =>
        !isDuplicateBug(bug) &&
        !isNotAnalyzedBug(bug) &&
        (bug.status === "failed" ||
            !bug.analysis ||
            typeof bug.analysis !== "object");

    const isAnalyzedBug = bug =>
        !isDuplicateBug(bug) && !isNotAnalyzedBug(bug) && !isFailedBug(bug);

    const analyses = data.bugs.filter(isAnalyzedBug).map(bug => bug.analysis);
    const notAnalyzedCount = data.bugs.filter(isNotAnalyzedBug).length;

    const overviewHeading = document.createElement("h3");
    overviewHeading.className = "batch-summary-heading";
    overviewHeading.textContent = "Analysis Overview";
    resultGrid.appendChild(overviewHeading);

    const overview = document.createElement("div");
    overview.className = "batch-summary";

    const overviewFields = [
        ["Bugs", data.bugs.length],
        ["Analyzed", analyses.length],
        ["Failed", data.bugs.filter(isFailedBug).length],
        ["Duplicates", data.bugs.filter(isDuplicateBug).length],
        ...(notAnalyzedCount ? [["Not analyzed", notAnalyzedCount]] : [])
    ];

    overviewFields.forEach(([labelText, valueText]) => {
        const item = document.createElement("div");
        item.className = "result-item";

        const label = document.createElement("div");
        label.className = "result-label";
        label.textContent = labelText;

        const value = document.createElement("div");
        value.className = "summary-overview-value";
        value.textContent = valueText;

        item.appendChild(label);
        item.appendChild(value);
        overview.appendChild(item);
    });

    resultGrid.appendChild(overview);

    const summaryHeading = document.createElement("h3");
    summaryHeading.className = "batch-summary-heading";
    summaryHeading.textContent = "Batch Summary";
    resultGrid.appendChild(summaryHeading);

    const summary = document.createElement("div");
    summary.className = "summary-panel";

    const summaryFields = [
        ["Severity", "severity", ["CRITICAL", "HIGH", "MEDIUM", "LOW"]],
        ["Priority", "priority", ["P1", "P2", "P3", "P4"]],
        ["Category", "category", []]
    ];

    const CATEGORY_VISIBLE_LIMIT = 5;

    const createSummaryChip = (key, countLabel, countValue) => {
        const chip = document.createElement("span");
        chip.className = "summary-chip";
        if (key === "severity") {
            chip.classList.add(`severity-${countLabel.toLowerCase()}`);
        }
        chip.setAttribute("aria-label", `${countLabel}: ${countValue}`);

        const text = document.createElement("span");
        text.textContent = countLabel;
        const count = document.createElement("span");
        count.className = "summary-chip-count";
        count.textContent = countValue;
        chip.append(text, count);
        return chip;
    };

    summaryFields.forEach(([labelText, key, preferredOrder]) => {
        const counts = analyses.reduce((result, analysis) => {
            const value = analysis[key] || "Unknown";
            result[value] = (result[value] || 0) + 1;
            return result;
        }, {});

        // Fixed scales keep their natural order; free-text values
        // such as categories are sorted by frequency.
        const countLabels = [
            ...preferredOrder.filter(value => counts[value]),
            ...Object.keys(counts)
                .filter(value => !preferredOrder.includes(value))
                .sort((a, b) => counts[b] - counts[a] || a.localeCompare(b)),
        ];

        const row = document.createElement("div");
        row.className = "summary-row";

        const label = document.createElement("div");
        label.className = "summary-row-label";
        label.textContent = labelText;

        const chips = document.createElement("div");
        chips.className = "summary-chip-list";

        countLabels.forEach((countLabel, chipIndex) => {
            const chip = createSummaryChip(key, countLabel, counts[countLabel]);
            if (key === "category" && chipIndex >= CATEGORY_VISIBLE_LIMIT) {
                chip.hidden = true;
            }
            chips.appendChild(chip);
        });

        const hiddenCount = countLabels.length - CATEGORY_VISIBLE_LIMIT;

        if (key === "category" && hiddenCount > 0) {
            const toggle = document.createElement("button");
            toggle.type = "button";
            toggle.className = "summary-more-toggle";
            toggle.textContent = `+${hiddenCount} more`;
            toggle.setAttribute("aria-expanded", "false");

            toggle.addEventListener("click", () => {
                const expanded = toggle.getAttribute("aria-expanded") !== "true";
                toggle.setAttribute("aria-expanded", String(expanded));
                toggle.textContent = expanded ? "Show less" : `+${hiddenCount} more`;

                [...chips.children]
                    .slice(CATEGORY_VISIBLE_LIMIT, countLabels.length)
                    .forEach(chip => {
                        chip.hidden = !expanded;
                    });
            });

            chips.appendChild(toggle);
        }

        if (!countLabels.length) {
            chips.textContent = "—";
        }

        row.append(label, chips);
        summary.appendChild(row);
    });

    resultGrid.appendChild(summary);

    // A duplicate has no analysis of its own, so it points at the
    // original and says when the original has no analysis either.
    const describeDuplicate = bug => {
        const original = data.bugs[bug.duplicate_of - 1];
        const base = `This bug is a duplicate of Bug ${bug.duplicate_of}`;

        if (original && isNotAnalyzedBug(original)) {
            return `${base}, which was not analyzed because Ollama became unavailable.`;
        }
        if (original && isFailedBug(original)) {
            return `${base}, which could not be analyzed.`;
        }
        return `${base}.`;
    };

    data.bugs.forEach((bug, index) => {
        const isFailed = isFailedBug(bug);
        const isDuplicate = isDuplicateBug(bug);
        const isNotAnalyzed = isNotAnalyzedBug(bug);
        const hasNoAnalysis = isFailed || isDuplicate || isNotAnalyzed;
        const duplicateMessage = isDuplicate ? describeDuplicate(bug) : "";
        const excelValues = bug.bug || {};
        const analysis = isFailed || isNotAnalyzed
            ? {
                priority: excelValues.priority,
                category: excelValues.category,
                missing_information:
                    bug.error || "The bug could not be analyzed."
            }
            : isDuplicate
                ? { missing_information: duplicateMessage }
                : bug.analysis;

        const bugCard = document.createElement("details");
        bugCard.className = "batch-bug-card";
        bugCard.classList.toggle("is-failed", isFailed);
        bugCard.classList.toggle("is-duplicate", isDuplicate);
        bugCard.classList.toggle("is-not-analyzed", isNotAnalyzed);

        const heading = document.createElement("summary");
        heading.className = "batch-bug-header";

        const title = document.createElement("span");
        title.className = "batch-bug-title";
        title.textContent = `Bug ${index + 1}: ${bug.title || "Untitled"}`;

        heading.appendChild(title);

        const severity = analysis.severity;

        if (isFailed) {
            const failedBadge = document.createElement("span");
            failedBadge.className = "severity-badge status-failed";
            failedBadge.textContent = "FAILED";

            const failedTooltip = bug.error || "The bug could not be analyzed.";

            failedBadge.setAttribute("data-tooltip", failedTooltip);
            failedBadge.setAttribute("aria-label", failedTooltip);

            heading.appendChild(failedBadge);
        } else if (isNotAnalyzed) {
            const notAnalyzedBadge = document.createElement("span");
            notAnalyzedBadge.className = "severity-badge status-not-analyzed";
            notAnalyzedBadge.textContent = "NOT ANALYZED";

            notAnalyzedBadge.setAttribute("data-tooltip", bug.error);
            notAnalyzedBadge.setAttribute("aria-label", bug.error);

            heading.appendChild(notAnalyzedBadge);
        } else if (isDuplicate) {
            const duplicateBadge = document.createElement("span");
            duplicateBadge.className = "severity-badge status-duplicate";
            duplicateBadge.textContent = `DUPLICATE OF BUG ${bug.duplicate_of}`;

            duplicateBadge.setAttribute("data-tooltip", duplicateMessage);
            duplicateBadge.setAttribute("aria-label", duplicateMessage);

            heading.appendChild(duplicateBadge);
        } else if (severity !== undefined && severity !== null) {
            const severityBadge = document.createElement("span");
            severityBadge.className = `severity-badge severity-${String(severity).toLowerCase()}`;
            severityBadge.textContent = severity;

            const severityTooltip =
                "How much impact the bug has on the system or user experience. Critical issues may block a major function or make the application unusable.";

            severityBadge.setAttribute("data-tooltip", severityTooltip);
            severityBadge.setAttribute("aria-label", severityTooltip);

            heading.appendChild(severityBadge);
        }

        bugCard.appendChild(heading);

        const bugContent = document.createElement("div");
        bugContent.className = "batch-bug-content";

        Object.entries(labels).forEach(([key, labelText]) => {
            const item = document.createElement("div");
            item.className = "result-item";

            const label = document.createElement("div");
            label.className = "result-label";

            const labelTextElement = document.createElement("span");
            labelTextElement.textContent = labelText;

            label.appendChild(labelTextElement);

            const tooltipTexts = {
                severity:
                    "How much impact the bug has on the system or user experience. Critical issues may block a major function or make the application unusable.",

                priority:
                    "How urgently the bug should be fixed from a product and business perspective. Higher priority means the issue should be addressed sooner.",

                category:
                    "The type of problem identified in the bug report. Examples include Functional, UI, Performance, Security, Compatibility, and Data.",

                impact:
                    "Describes how the bug affects users, business operations, system functionality, or the overall user experience.",

                possible_root_cause:
                    "A likely technical or logical reason behind the observed bug. This is an analysis hypothesis and may require further investigation.",

                missing_information:
                    "Important details that are missing from the bug report and could help QA investigate, reproduce, or validate the issue more effectively.",

                confidence:
                    "Indicates how confident the analysis is based on the information provided in the bug report. Higher confidence means the available information provides stronger support for the analysis."
            };

            const tooltipText = tooltipTexts[key];

            if (tooltipText) {
                const info = document.createElement("span");

                info.className = "info-tooltip";
                info.textContent = "i";
                info.setAttribute("data-tooltip", tooltipText);
                info.setAttribute("aria-label", tooltipText);

                label.appendChild(info);
            }

            const value = document.createElement("div");
            value.className = "result-value";
            value.textContent = hasNoAnalysis
                ? analysis[key] || "—"
                : formatAnalysisValue(key, analysis[key]);

            item.append(label, value);
            bugContent.appendChild(item);
        });

        bugCard.appendChild(bugContent);

        bugContent.hidden = true;

        heading.addEventListener("click", () => {
            bugContent.hidden = !bugContent.hidden;
        });


        const suggestedScenarios = analysis.suggested_test_scenarios;

        if (Array.isArray(suggestedScenarios) && suggestedScenarios.length) {
            const scenariosCard = document.createElement("div");
            scenariosCard.className = "suggested-scenarios-card";

            // Accordion header
            const accordionHeader = document.createElement("div");
            accordionHeader.className = "suggested-scenarios-header";

            const headerLeft = document.createElement("div");
            headerLeft.className = "suggested-scenarios-header-left";

            const arrow = document.createElement("span");
            arrow.className = "suggested-scenarios-arrow";
            arrow.textContent = "›";

            const labelText = document.createElement("span");
            labelText.textContent = "Suggested Test Scenarios";

            const info = document.createElement("span");
            info.className = "info-tooltip";
            info.textContent = "i";

            const tooltipText =
                "AI-generated test scenarios designed to validate the reported bug and verify the expected behavior after the fix. Each scenario includes the test case, expected result, purpose, category, and priority.";

            info.setAttribute("data-tooltip", tooltipText);
            info.setAttribute("aria-label", tooltipText);

            headerLeft.appendChild(arrow);
            headerLeft.appendChild(labelText);
            headerLeft.appendChild(info);

            accordionHeader.appendChild(headerLeft);

            // Accordion content
            const scenarios = document.createElement("div");
            scenarios.className = "test-scenarios";
            scenarios.hidden = true;

            suggestedScenarios.forEach((testCase) => {
                const scenario = document.createElement("div");
                scenario.className = "test-scenario";

                const header = document.createElement("div");
                header.className = "test-scenario-header";

                const id = document.createElement("span");
                id.className = "test-case-id";
                id.textContent = testCase.test_case_id || "Test Case";

                const meta = document.createElement("div");
                meta.className = "test-case-meta";
                meta.textContent = testCase.category || "QA Validation";

                const priority = document.createElement("span");
                const priorityValue = String(
                    testCase.priority || "Medium"
                ).toLowerCase();

                priority.className = `test-case-priority ${priorityValue}`;
                priority.textContent = testCase.priority || "Medium";

                header.appendChild(id);
                header.appendChild(meta);
                header.appendChild(priority);

                const scenarioSection = document.createElement("div");
                scenarioSection.className = "test-case-section";

                const scenarioLabel = document.createElement("div");
                scenarioLabel.className = "test-case-section-label";
                scenarioLabel.textContent = "Scenario";

                const scenarioText = document.createElement("div");
                scenarioText.className = "test-case-section-text";
                scenarioText.textContent = testCase.scenario || "";

                scenarioSection.appendChild(scenarioLabel);
                scenarioSection.appendChild(scenarioText);

                const expectedSection = document.createElement("div");
                expectedSection.className = "test-case-section";

                const expectedLabel = document.createElement("div");
                expectedLabel.className = "test-case-section-label";
                expectedLabel.textContent = "Expected Result";

                const expectedText = document.createElement("div");
                expectedText.className = "test-case-section-text";
                expectedText.textContent = testCase.expected_result || "";

                expectedSection.appendChild(expectedLabel);
                expectedSection.appendChild(expectedText);

                const purposeSection = document.createElement("div");
                purposeSection.className = "test-case-section";

                const purposeLabel = document.createElement("div");
                purposeLabel.className = "test-case-section-label";
                purposeLabel.textContent = "Purpose";

                const purposeText = document.createElement("div");
                purposeText.className = "test-case-section-text";
                purposeText.textContent = testCase.purpose || "";

                purposeSection.appendChild(purposeLabel);
                purposeSection.appendChild(purposeText);

                scenario.appendChild(header);
                scenario.appendChild(scenarioSection);
                scenario.appendChild(expectedSection);
                scenario.appendChild(purposeSection);

                scenarios.appendChild(scenario);
            });

            scenariosCard.appendChild(accordionHeader);
            scenariosCard.appendChild(scenarios);

            // Closed by default
            accordionHeader.addEventListener("click", () => {
                scenarios.hidden = !scenarios.hidden;
                scenariosCard.classList.toggle(
                    "is-open",
                    !scenarios.hidden
                );
            });

            // IMPORTANT:
            // Keep Suggested Test Scenarios inside the current bug card
            bugContent.appendChild(scenariosCard);
        }
        resultGrid.appendChild(bugCard);
    });
    resultCard.classList.add("visible");
}

/*
 * Analysis
 */

/*
 * Waiting for another analysis
 */

const waitModal = document.getElementById("waitModal");
const waitModalTitle = document.getElementById("waitModalTitle");
const waitModalMessage = document.getElementById("waitModalMessage");
const waitModalConfirm = document.getElementById("waitModalConfirm");
const waitModalCancel = document.getElementById("waitModalCancel");
let closeWaitModal = null;

// What runs in any tab of this app; null when the check fails, so
// the analysis then starts without a warning.
async function fetchActivity() {
    try {
        const response = await fetch("/bugs/activity", { cache: "no-store" });
        return response.ok ? await response.json() : null;
    } catch {
        return null;
    }
}

// Resolves to true when the user starts the analysis anyway.
function confirmWaiting({ title, message, confirmText }) {
    waitModalTitle.textContent = title;
    waitModalMessage.textContent = message;
    waitModalConfirm.textContent = confirmText;
    waitModal.hidden = false;
    document.body.style.overflow = "hidden";
    waitModalConfirm.focus();

    return new Promise(resolve => {
        closeWaitModal = confirmed => {
            waitModal.hidden = true;
            document.body.style.overflow = "";
            closeWaitModal = null;
            resolve(confirmed);
        };
    });
}

waitModalConfirm.addEventListener("click", () => closeWaitModal?.(true));
waitModalCancel.addEventListener("click", () => closeWaitModal?.(false));
waitModal
    .querySelector(".diagnosis-modal-backdrop")
    .addEventListener("click", () => closeWaitModal?.(false));
document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
        closeWaitModal?.(false);
    }
});

// Ollama analyzes one request at a time, so an analysis started while
// one of the other kind runs (in any tab) waits for it. The user is
// told and can still cancel; false means do not start.
async function confirmStartWhileOtherRuns(mode, button) {
    button.disabled = true;
    const activity = await fetchActivity();
    refreshAnalyzeButtons();

    const otherRunning =
        mode === "single" ? activity?.batch_running : activity?.single_running;
    if (!otherRunning) {
        return true;
    }

    const confirmed = await confirmWaiting(
        mode === "single"
            ? {
                title: "A batch analysis is running",
                message:
                    "Ollama analyzes one request at a time, so this bug will be " +
                    "analyzed between the batch's bugs and may take a few minutes " +
                    "longer than usual.",
                confirmText: "Analyze anyway"
            }
            : {
                title: "A single bug analysis is running",
                message:
                    "Ollama analyzes one request at a time, so the batch will wait " +
                    "until the single bug analysis finishes, usually within a minute.",
                confirmText: "Start batch"
            }
    );

    // The service may have become unavailable meanwhile.
    return confirmed && !button.disabled;
}

bugForm.addEventListener("submit", async event => {
    event.preventDefault();

    if (!validateForm()) {
        return;
    }

    if (!(await confirmStartWhileOtherRuns("single", analyzeButton))) {
        return;
    }

    setSavedResult("single", null);

    const submittedBug = {
        title: fields.bugTitle.input.value.trim(),
        description: fields.description.input.value.trim(),
        steps_to_reproduce: fields.stepsToReproduce.input.value.trim(),
        expected_result: fields.expectedResult.input.value.trim(),
        actual_result: fields.actualResult.input.value.trim()
    };

    const formData = new FormData();

    formData.append(
        "title",
        fields.bugTitle.input.value.trim()
    );

    formData.append(
        "description",
        fields.description.input.value.trim()
    );

    // Sent as written; the server splits it into steps and removes
    // list markers such as "1." or "-" (app/services/steps.py).
    formData.append(
        "steps_to_reproduce",
        fields.stepsToReproduce.input.value.trim()
    );

    formData.append(
        "expected_result",
        fields.expectedResult.input.value.trim()
    );

    formData.append(
        "actual_result",
        fields.actualResult.input.value.trim()
    );

    selectedScreenshots.forEach((file) => {
        formData.append("screenshots", file);
    });

    const abortController = new AbortController();
    singleAbortController = abortController;

    singleAnalysisRunning = true;
    refreshAnalyzeButtons();
    runningAnalyses += 1;

    analyzeButton.innerHTML = `
            <span class="loading">
                <span class="spinner"></span>
                Analyzing...
            </span>
        `;

    try {
        const response = await fetch("/bugs/analyze", {
            method: "POST",
            body: formData,
            signal: abortController.signal
        });

        let data;

        try {
            data = await response.json();
        } catch {
            data = await response.text();
        }

        if (!response.ok) {
            // 503 means Ollama or the LLM failed; the service status
            // shown at the top may be out of date.
            if (response.status === 503) {
                checkServiceStatus();
            }

            throw data;
        }

        // The values are kept with the result for the Excel report.
        setSavedResult("single", { type: "result", data, bug: submittedBug });

    } catch (error) {
        if (abortController.signal.aborted) {
            return;
        }

        setSavedResult("single", { type: "error", message: formatError(error) });

    } finally {
        if (singleAbortController === abortController) {
            singleAbortController = null;
        }
        runningAnalyses -= 1;
        singleAnalysisRunning = false;
        refreshAnalyzeButtons();
        analyzeButton.textContent = "Analyze Bug";
    }
});

/*
 * Clear
 */

clearButton.addEventListener("click", () => {
    if (singleAbortController) {
        singleAbortController.abort();
    }
    bugForm.reset();
    clearValidation();
    setSavedResult("single", null);

    // Clear screenshot
    selectedScreenshots = [];
    screenshotInput.value = "";
    renderScreenshots();
    showScreenshotNotice([]);

    fields.bugTitle.input.focus();
});

// Prefix of batch errors caused by Ollama or the LLM (see app/api/bugs.py).
const LLM_ERROR_PREFIX = "The LLM could not analyze this bug";

const SERVICE_STATUS_LABELS = {
    checking: "Checking...",
    available: "Available",
    unavailable: "Unavailable"
};

// The only place that changes the service status at the top, so the
// status, the diagnosis button and both analyze buttons stay in sync.
function setServiceStatus(status) {
    serviceStatus = status;

    statusDot.classList.remove("checking", "available", "unavailable");
    statusDot.classList.add(status);
    serviceValue.textContent = SERVICE_STATUS_LABELS[status];

    if (status === "checking") {
        diagnosisButton.style.display = "none";
    } else {
        const available = status === "available";

        diagnosisButton.textContent = available ? "✓" : "⚠";
        diagnosisButton.classList.toggle("diagnosis-available", available);
        diagnosisButton.style.display = "flex";
    }

    refreshAnalyzeButtons();
    scheduleServiceRecheck();
}

// The status is checked again in the background so it follows Ollama:
// - unavailable: a full check every 10 seconds, so it recovers on its
//   own when Ollama comes back;
// - available: a light check every 30 seconds (no inference), so it
//   notices when Ollama stops.
// Checks pause while the tab is hidden and run when it becomes visible.
const SERVICE_RECHECK_INTERVAL_MS = 10000;
const SERVICE_LIGHT_CHECK_INTERVAL_MS = 30000;
let serviceRecheckTimer = null;
let serviceRecheckRunning = false;

function scheduleServiceRecheck() {
    clearTimeout(serviceRecheckTimer);
    serviceRecheckTimer = null;

    if (serviceStatus === "checking") {
        return;
    }

    serviceRecheckTimer = setTimeout(
        recheckService,
        serviceStatus === "unavailable"
            ? SERVICE_RECHECK_INTERVAL_MS
            : SERVICE_LIGHT_CHECK_INTERVAL_MS
    );
}

async function isOllamaReachable() {
    try {
        const response = await fetch("/health/ollama", { cache: "no-store" });
        const data = await response.json();
        return response.ok && data.available === true;
    } catch {
        return false;
    }
}

async function recheckService() {
    clearTimeout(serviceRecheckTimer);
    serviceRecheckTimer = null;

    if (serviceStatus === "checking" || document.hidden || serviceRecheckRunning) {
        return;
    }

    serviceRecheckRunning = true;

    try {
        if (serviceStatus === "available") {
            if (await isOllamaReachable()) {
                scheduleServiceRecheck();
            } else {
                // Run the full check so the reason is ready in the
                // diagnosis window.
                await checkServiceStatus();
            }
            return;
        }

        // Updates the status (and schedules the next check) and the
        // diagnosis window.
        await runDiagnosis();
    } finally {
        serviceRecheckRunning = false;
    }
}

document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
        recheckService();
    }
});

function renderDiagnosisMessage(statusClass, statusLabel, message) {
    serviceDiagnosisMessage.innerHTML = `
            <div class="diagnosis-item">
                <div class="diagnosis-item-header">
                    <span class="diagnosis-status-dot ${statusClass}"></span>
                    <span class="diagnosis-item-title">Connection Check</span>
                    <span class="diagnosis-status-text ${statusClass}">${statusLabel}</span>
                </div>
                <div class="diagnosis-item-message">${escapeHtml(message)}</div>
            </div>
        `;
}

// Runs the full diagnosis and updates both the diagnosis window and
// the status at the top from the same result.
async function runDiagnosis() {
    const data = await getAnalysisDiagnosisData();

    if (!data) {
        renderDiagnosisMessage(
            "unavailable",
            "Failed",
            "Could not connect to the analysis service."
        );
        setServiceStatus("unavailable");
        return;
    }

    serviceDiagnosisMessage.innerHTML = getAnalysisDiagnosis(data);
    setServiceStatus(data.available ? "available" : "unavailable");
}

/*
 * Health check
 */

async function checkServiceStatus() {
    setServiceStatus("checking");

    // The diagnosis also fills the diagnosis window, so the reason is
    // ready when the user opens it.
    await runDiagnosis();
}

/*
 * Diagnosis window and Retry Connection
 */

async function refreshDiagnosis() {
    diagnosisRetryButton.disabled = true;
    diagnosisRetryButton.textContent = "Checking...";

    renderDiagnosisMessage(
        "checking",
        "Checking",
        "Checking Ollama, required model and inference..."
    );

    try {
        await runDiagnosis();
    } finally {
        diagnosisRetryButton.disabled = false;
        diagnosisRetryButton.textContent = "Retry Connection";
    }
}

diagnosisButton.addEventListener("click", () => {
    diagnosisModal.hidden = false;
    document.body.style.overflow = "hidden";

    refreshDiagnosis();
});


diagnosisCloseButton.addEventListener("click", () => {
    diagnosisModal.hidden = true;
    document.body.style.overflow = "";
});


document
    .querySelector(".diagnosis-modal-backdrop")
    .addEventListener("click", () => {
        diagnosisModal.hidden = true;
        document.body.style.overflow = "";
    });


document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
        diagnosisModal.hidden = true;
        document.body.style.overflow = "";
    }
});


diagnosisModal.addEventListener("click", (event) => {
    if (event.target === diagnosisModal) {
        diagnosisModal.hidden = true;
        document.body.style.overflow = "";
    }
});


/*
 * Retry Connection button
 */

diagnosisRetryButton.addEventListener("click", refreshDiagnosis);


/*
 * Initial service check
 */

checkServiceStatus();

/*
 * Excel export
 */

// The file name the server chose, from the Content-Disposition header.
function downloadName(response, fallback) {
    const header = response.headers.get("Content-Disposition") || "";
    const match = header.match(/filename="([^"]+)"/);
    return match ? match[1] : fallback;
}

exportButton.addEventListener("click", async () => {
    const mode = activeMode;
    const saved = savedResults[mode];
    if (!saved || saved.type !== "result") {
        return;
    }

    const request = mode === "single"
        ? { url: "/bugs/export/single", body: { bug: saved.bug, analysis: saved.data } }
        : {
            url: "/bugs/export/batch",
            body: {
                source_name: saved.data.source_name || null,
                bugs: saved.data.bugs.map(bug => ({
                    row: bug.row,
                    status: bug.status,
                    bug: bug.bug,
                    analysis: bug.analysis,
                    error: bug.error,
                    duplicate_of: bug.duplicate_of
                }))
            }
        };

    exportButton.disabled = true;
    exportError.hidden = true;

    try {
        const response = await fetch(request.url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(request.body)
        });

        if (!response.ok) {
            let detail;
            try {
                detail = await response.json();
            } catch {
                detail = `The report could not be created (HTTP ${response.status}).`;
            }
            throw detail;
        }

        const blob = await response.blob();
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = downloadName(response, "analysis-report.xlsx");
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    } catch (error) {
        exportError.textContent = `Export failed: ${formatError(error)}`;
        exportError.hidden = false;
    } finally {
        exportButton.disabled = false;
    }
});
