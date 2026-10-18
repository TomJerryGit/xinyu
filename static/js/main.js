/* 心语 V9.2 前端控制器
 * 约定：
 *  - 所有来自后端/用户/AI 的文本写入 HTML 前必须 esc()
 *  - 不保留旧版 UI 的失效引用
 *  - 每个入口在 pywebview 未就绪时安全失败
 */
'use strict';

const $ = (id) => document.getElementById(id);
const state = {
    initDone: false,
    candidates: [],
    candidateIndex: 0,
    genre: '五言绝句',
    topic: '',
    vertical: false,
    teaching: null,
    quiz: null,
    timer: null,
    timeLeft: 60,
    wrongBook: [],
    learned: [],
    panelCat: '',
    panelKeyword: '',
    panelPage: 1,
    panelPages: 1,
    panelTotal: 0,
    panelPageSize: 18,
    panelItems: [],
    preview: [],
    previewSelected: new Set(),
    chatHistory: [],
    speakContent: '',
    speakLines: [],
    speakIndex: 0,
    speakUtterance: null,
    typingTimer: null,
    apiProviders: [],
    dashboard: null,
    daily: null,
    theme: 'paper',
    cmdkIndex: 0,
    cmdkItems: [],
    skipClassicsLoad: false,
    currentJobId: null,
    uiState: {},
    verifiedOnly: false,
    wordNotes: null,
    wordAllusions: [],
    intertext: [],
};

/* ---------------- 基础工具 ---------------- */
function esc(value) {
    return String(value === null || value === undefined ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function fmtNumber(value) {
    const number = Number(value || 0);
    return Number.isFinite(number) ? number.toLocaleString() : '0';
}

function showToast(message, type = 'info', duration = 3000) {
    const container = $('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = String(message || '');
    container.appendChild(toast);
    setTimeout(() => {
        toast.classList.add('toast-hide');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

function showStatus(message) {
    const bar = $('statusBar');
    if (!bar) return;
    bar.textContent = String(message || '');
    bar.classList.add('show');
    clearTimeout(showStatus._timer);
    showStatus._timer = setTimeout(() => bar.classList.remove('show'), 2600);
}

function showLoading(targetId, text = '加载中...') {
    const target = $(targetId);
    if (!target) return;
    let overlay = target.querySelector('.loading-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.className = 'loading-overlay';
        overlay.innerHTML = `<div class="spinner"></div><span>${esc(text)}</span>`;
        target.appendChild(overlay);
    }
    overlay.style.display = 'flex';
}

function hideLoading(targetId) {
    const target = $(targetId);
    if (!target) return;
    const overlay = target.querySelector('.loading-overlay');
    if (overlay) overlay.style.display = 'none';
}

const API_DEADLINE = Date.now() + 8000;

function apiReady() {
    if (typeof pywebview === 'undefined' || !pywebview || !pywebview.api) return false;
    if (typeof pywebview.api.get_settings === 'function') return true;
    return Date.now() > API_DEADLINE;
}

function callApi(name, ...args) {
    if (!apiReady()) return Promise.reject(new Error('pywebview 尚未就绪'));
    let result;
    try {
        result = pywebview.api[name](...args);
    } catch (error) {
        return Promise.reject(error);
    }
    return Promise.resolve(result).then((data) => {
        if (data && typeof data === 'object' && data.__error__) {
            const info = data.__error__;
            const error = new Error(info.message || '操作失败');
            error.code = info.code || 'INTERNAL';
            error.detail = info.detail || '';
            throw error;
        }
        return data;
    });
}

function withTimeout(promise, ms, label = '请求') {
    return Promise.race([
        promise,
        new Promise((_, reject) => setTimeout(() => reject(new Error(`${label}超时`)), ms)),
    ]);
}

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function showJobCancel(show) {
    let button = $('jobCancel');
    if (show && !button) {
        button = document.createElement('button');
        button.id = 'jobCancel';
        button.className = 'primary-btn';
        button.textContent = '取消任务';
        button.style.cssText = 'position:fixed;right:20px;bottom:46px;z-index:2500;box-shadow:var(--shadow-lg)';
        button.onclick = cancelCurrentJob;
        document.body.appendChild(button);
    }
    if (button) button.style.display = show ? 'block' : 'none';
}

async function cancelCurrentJob() {
    if (!state.currentJobId) return;
    await guarded('取消任务', () => callApi('cancel_job', state.currentJobId), { toastError: false });
    showToast('正在取消任务…', 'info');
}

async function runJob(kind, payload, options = {}) {
    const submitted = await callApi('submit_job', kind, JSON.stringify(payload || {}));
    if (!submitted || submitted.error) {
        throw new Error((submitted && submitted.error) || '任务提交失败');
    }
    state.currentJobId = submitted.job_id;
    showJobCancel(true);
    const started = Date.now();
    const timeout = options.timeout || 300000;
    try {
        while (Date.now() - started < timeout) {
            await sleep(550);
            const job = await callApi('get_job', state.currentJobId);
            if (!job || job.error) throw new Error((job && job.error) || '任务不存在');
            if (options.onProgress) options.onProgress(job);
            if (job.status === 'done') return job.result;
            if (job.status === 'failed') throw new Error(job.error || job.message || '任务失败');
            if (job.status === 'cancelled') throw new Error('任务已取消');
            if (job.status === 'interrupted') throw new Error('任务因应用退出而中断');
        }
        throw new Error('任务超时');
    } finally {
        state.currentJobId = null;
        showJobCancel(false);
    }
}

async function guarded(label, fn, options = {}) {
    const { timeout = 0, loading = '', toastError = true } = options;
    try {
        if (loading) showLoading(loading, `${label}...`);
        const promise = fn();
        return timeout ? await withTimeout(promise, timeout, label) : await promise;
    } catch (error) {
        if (toastError) showToast(`${label}失败：${error.message || error}`, 'error', 4200);
        return null;
    } finally {
        if (loading) hideLoading(loading);
    }
}

function safeGet(key, fallback) {
    try {
        const raw = localStorage.getItem(key);
        return raw ? JSON.parse(raw) : fallback;
    } catch (error) {
        return fallback;
    }
}

function safeSet(key, value) {
    try {
        localStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
        /* 隐私模式或容量不足时静默失败 */
    }
}

function persistUiState(patch) {
    state.uiState = Object.assign({}, state.uiState || {}, patch);
    try {
        Promise.resolve(callApi('save_ui_state', JSON.stringify(patch))).catch(() => {});
    } catch (error) {
        /* UI 状态持久化失败不影响功能 */
    }
}

function loadUiList(uiKey, localKey, fallback = []) {
    const fromUi = state.uiState ? state.uiState[uiKey] : null;
    if (Array.isArray(fromUi)) return fromUi;
    return safeGet(localKey, fallback);
}

/* ---------------- 主题 ---------------- */
const THEMES = ['paper', 'ink', 'dark'];

function setTheme(name, persist = true) {
    const theme = THEMES.includes(name) ? name : 'paper';
    state.theme = theme;
    document.body.className = `theme-${theme}`;
    if (persist) {
        safeSet('themeV92', theme);
        persistUiState({ theme });
    }
    const select = $('themeSelect');
    if (select) select.value = theme;
    const button = $('themeBtn');
    if (button) button.title = `当前主题：${theme}`;
}

function cycleTheme() {
    const index = THEMES.indexOf(state.theme);
    setTheme(THEMES[(index + 1) % THEMES.length]);
    showStatus(`主题：${state.theme}`);
}

/* ---------------- 初始化 ---------------- */
async function initApp() {
    if (state.initDone) return;
    if (!apiReady()) return;
    state.initDone = true;

    let ui = {};
    try {
        ui = (await callApi('get_ui_state')) || {};
    } catch (error) {
        ui = {};
    }
    state.uiState = ui;
    state.theme = ui.theme || safeGet('themeV92', 'paper');
    setTheme(state.theme, false);
    state.wrongBook = loadUiList('wrong_book', 'wrongBook', []);
    state.learned = loadUiList('learned', 'learnedWorks', []);
    updateTeachProgress();

    bindChat();
    bindShortcuts();
    updateCreationStyles();
    loadTtsOptions();
    const lastNav = ui.last_nav || safeGet('lastNavV92', 'dashboard');
    switchNav(lastNav);
    if (lastNav !== 'dashboard') loadDashboard();
    loadChatHistory();
}

function bindChat() {
    const input = $('chatInput');
    if (!input || input.dataset.bound) return;
    input.dataset.bound = '1';
    input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            sendChat();
        }
    });
}

function bindShortcuts() {
    document.addEventListener('keydown', (event) => {
        const key = event.key.toLowerCase();
        if ((event.ctrlKey || event.metaKey) && key === 'k') {
            event.preventDefault();
            openCmdk();
        } else if (event.key === 'Escape') {
            if (document.body.classList.contains('classroom-mode') || document.body.classList.contains('student-mode')) {
                exitClassroomModes();
            } else if ($('teachEditor') && !$('teachEditor').classList.contains('hidden')) {
                closeTeachingEditor();
            }
        } else if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
            event.preventDefault();
            if ($('tab-creation').classList.contains('active')) doCreation();
        } else if ((event.ctrlKey || event.metaKey) && key === 's') {
            event.preventDefault();
            saveCreation();
        } else if (event.key === 'Escape') {
            closeCmdk();
            closeClassicsPanel();
            closeSpeakPanel();
        }
    });
}

window.addEventListener('pywebviewready', initApp);
const initTimer = setInterval(() => {
    if (apiReady()) {
        clearInterval(initTimer);
        initApp();
    }
}, 120);
setTimeout(() => clearInterval(initTimer), 9000);

/* ---------------- 导航 ---------------- */
const NAV_NAMES = {
    dashboard: '概览',
    creation: '创作',
    appreciation: '赏析',
    teaching: '教学',
    quiz: '题库',
    classics: '经典文库',
    data: '数据管理',
    settings: '设置',
};

function switchNav(moduleName) {
    if (!NAV_NAMES[moduleName]) moduleName = 'dashboard';
    document.querySelectorAll('.nav-btn').forEach((button) => {
        button.classList.toggle('active', button.textContent === NAV_NAMES[moduleName]);
    });
    document.querySelectorAll('.tab-content').forEach((panel) => panel.classList.remove('active'));
    const panel = $(`tab-${moduleName}`);
    if (panel) panel.classList.add('active');

    closeClassicsPanel();
    closeSpeakPanel();
    renderSidebar(moduleName);
    safeSet('lastNavV92', moduleName);
    persistUiState({ last_nav: moduleName });

    if (moduleName === 'dashboard') loadDashboard();
    if (moduleName === 'settings') loadAiBudget();
    if (moduleName === 'classics' && !state.skipClassicsLoad) showClassicsCategories();
    state.skipClassicsLoad = false;
    if (moduleName === 'teaching') {
        loadTeachCats();
        updateTeachProgress();
    }
    if (moduleName === 'settings') {
        updateApiStatus();
        loadSettingsExtras();
    }
    if (moduleName === 'data') loadAiReview();
    if (moduleName === 'data') loadBackups();
}

const SIDEBAR_MENUS = {
    dashboard: [
        ['每日一诗', openDaily],
        ['随机经典', getRandomClassic],
        ['用量统计', loadUsageDashboard],
        ['立即备份', createBackup],
    ],
    creation: [
        ['随机主题', randomTopic],
        ['续写', continueMode],
        ['品评', critiqueWork],
        ['保存作品', saveCreation],
        ['导出TXT', exportTxt],
        ['导出图片', exportImage],
        ['导出信笺', exportLetter],
    ],
    appreciation: [
        ['搜索作品', doAppreciation],
        ['随机经典', getRandomClassic],
        ['我的收藏', showFavorites],
    ],
    teaching: [
        ['刷新分类', loadTeachCats],
        ['开始教学', startTeaching],
        ['学习进度', updateTeachProgress],
        ['查看笔记', () => renderNotes($('teachArtSelect') && $('teachArtSelect').value)],
    ],
    quiz: [
        ['生成试卷', startQuiz],
        ['限时挑战', startTimedQuiz],
        ['错题本', openWrongBook],
        ['历史记录', loadQuizHistory],
    ],
    classics: [
        ['全部分类', showClassicsCategories],
        ['唐诗', () => openClassicsPanel('唐诗')],
        ['宋词', () => openClassicsPanel('宋词')],
        ['经部', () => openClassicsPanel('经部')],
        ['史部', () => openClassicsPanel('史部')],
        ['子部', () => openClassicsPanel('子部')],
        ['集部', () => openClassicsPanel('集部')],
        ['收藏夹', showFavorites],
    ],
    data: [
        ['数据库健康', runValidate],
        ['一键清洗', runCleanAndOrganize],
        ['质量报告', showQualityReport],
        ['用量统计', loadUsageDashboard],
        ['运行指标', loadMetrics],
        ['阅读历史', loadReadingHistory],
        ['创作画像', loadProfile],
        ['备份中心', loadBackups],
        ['快速扩充', startExpand],
        ['预览审核', previewExpand],
    ],
    settings: [
        ['API设置', openSettings],
        ['主题切换', cycleTheme],
        ['检查更新', checkUpdate],
        ['清理缓存', clearCache],
        ['关于', showAbout],
    ],
};

function renderSidebar(moduleName) {
    const sidebar = $('sidebar');
    if (!sidebar) return;
    sidebar.innerHTML = '';
    (SIDEBAR_MENUS[moduleName] || []).forEach(([label, handler]) => {
        const button = document.createElement('button');
        button.className = 'side-btn';
        button.textContent = label;
        button.onclick = () => handler();
        sidebar.appendChild(button);
    });
}

/* ---------------- 概览 ---------------- */
async function loadDashboard() {
    showLoading('tab-dashboard', '加载概览...');
    const data = await guarded('加载概览', () => callApi('get_dashboard'), { toastError: false });
    hideLoading('tab-dashboard');
    if (!data) return;
    state.dashboard = data;
    state.daily = data.daily;

    const now = new Date();
    const hour = now.getHours();
    const greeting = hour < 6 ? '夜深了，读到好句就早点休息。'
        : hour < 12 ? '早安，今天想读哪一首？'
        : hour < 18 ? '午后宜读诗，宜写字。'
        : '灯下读诗，正是一天好时候。';
    if ($('dashDate')) $('dashDate').textContent = `${now.getFullYear()} 年 ${now.getMonth() + 1} 月 ${now.getDate()} 日 · ${greeting}`;
    if ($('dashGreeting')) $('dashGreeting').textContent = `已收录 ${fmtNumber(data.classics_total)} 篇作品，累计 ${fmtNumber(data.total_chars)} 字。`;
    if ($('dashStreak')) $('dashStreak').textContent = `连续 ${data.streak || 0} 天`;

    if ($('statClassics')) $('statClassics').textContent = fmtNumber(data.classics_total);
    if ($('statChars')) $('statChars').textContent = `${fmtNumber(data.total_chars)} 字 · ${data.category_count} 类`;
    if ($('statWorks')) $('statWorks').textContent = fmtNumber(data.works);
    if ($('statFavorites')) $('statFavorites').textContent = fmtNumber(data.favorites);
    if ($('statNotes')) $('statNotes').textContent = `笔记 ${data.notes || 0} 条`;
    if ($('statStreak')) $('statStreak').textContent = data.streak || 0;

    if (data.daily && data.daily.title) {
        if ($('dailyTitle')) $('dailyTitle').textContent = `《${data.daily.title}》`;
        if ($('dailyMeta')) $('dailyMeta').textContent = `${data.daily.author || '佚名'} · ${data.daily.dynasty || ''} · ${data.daily.category || ''}`;
        if ($('dailyContent')) {
            const lines = String(data.daily.content || '').split('\n').filter((line) => line.trim());
            $('dailyContent').innerHTML = lines.slice(0, 6).map((line) => `<p>${esc(line)}</p>`).join('');
        }
    }

    const categories = $('dashCategories');
    if (categories) {
        categories.innerHTML = (data.categories || []).map((item) =>
            `<button class="chip" onclick="openClassicsPanel('${esc(item.category)}')">${esc(item.category)} · ${item.count}</button>`
        ).join('') || '<p class="muted">暂无分类</p>';
    }
    const dynasties = $('dashDynasties');
    if (dynasties) {
        dynasties.innerHTML = (data.dynasties || []).map((item) =>
            `<span class="chip static">${esc(item.dynasty)} · ${item.count}</span>`
        ).join('') || '<p class="muted">暂无朝代数据</p>';
    }

    const recent = $('recentReads');
    if (recent) {
        if (!data.recent_reads || !data.recent_reads.length) {
            recent.innerHTML = '<p class="muted">还没有阅读记录，去经典文库逛逛。</p>';
        } else {
            recent.innerHTML = data.recent_reads.map((item) =>
                `<button class="list-row" onclick="showPanelDetail('${esc(item.classic_id)}')">
                    <span><b>${esc(item.title)}</b><small>${esc(item.author)} · ${esc(item.category || '')}</small></span>
                    <span class="muted">${esc(String(item.read_at || '').slice(5, 16))}</span>
                </button>`
            ).join('');
        }
    }
}

function openDaily() {
    if (state.daily && state.daily.id) showPanelDetail(state.daily.id);
}

function openDailyInAppreciation() {
    if (!state.daily) return;
    if ($('appreciationTitle')) $('appreciationTitle').value = state.daily.title;
    switchNav('appreciation');
    doAppreciation();
}

function speakDaily() {
    if (!state.daily) return;
    state.speakContent = state.daily.content || '';
    openSpeakPanel();
}

/* ---------------- 创作 ---------------- */
const FALLBACK_STYLES = [
    { label: '盛唐·浪漫（李白）', instruction: '你是李白，想象奇崛、气势奔放，善用夸张与明月、酒、剑等意象。' },
    { label: '盛唐·沉郁（杜甫）', instruction: '你是杜甫，格律严谨、沉郁顿挫，关注家国与民生。' },
    { label: '盛唐·山水田园（王维）', instruction: '你是王维，诗中有画，空灵禅意。' },
    { label: '两宋·婉约（李清照）', instruction: '你是李清照，词风婉约细腻，善以日常物象写深沉情感。' },
    { label: '两宋·豪放（苏轼）', instruction: '你是苏轼，旷达超逸，词风豪放。' },
];

async function updateCreationStyles(attempt = 0) {
    const genre = $('creationGenre') ? $('creationGenre').value : '';
    const select = $('creationStyle');
    if (!select) return;
    const previous = select.value;
    select.innerHTML = '<option value="">默认风格</option>';
    const styles = await guarded('加载风格', () => callApi('get_styles', genre), { toastError: false });
    if (!Array.isArray(styles) || !styles.length) {
        if (attempt < 2) {
            setTimeout(() => updateCreationStyles(attempt + 1), 400);
            return;
        }
        FALLBACK_STYLES.forEach((style) => {
            const option = document.createElement('option');
            option.value = JSON.stringify(style);
            option.textContent = style.label;
            select.appendChild(option);
        });
        return;
    }
    styles.forEach((style) => {
        if (!style || !style.label) return;
        const option = document.createElement('option');
        option.value = JSON.stringify(style);
        option.textContent = style.label;
        select.appendChild(option);
    });
    if (previous) {
        const matched = Array.from(select.options).find((option) => option.value === previous);
        if (matched) select.value = previous;
    }
}

function selectedStyle() {
    const select = $('creationStyle');
    if (!select || !select.value) return null;
    try {
        return JSON.parse(select.value);
    } catch (error) {
        return { instruction: select.value };
    }
}

function currentPoem() {
    return state.candidates[state.candidateIndex] || '';
}

function applyVertical() {
    const target = $('creationResult');
    if (target) target.classList.toggle('vertical-poem', state.vertical);
}

function toggleVertical() {
    state.vertical = !state.vertical;
    applyVertical();
    showStatus(state.vertical ? '已切换竖排' : '已切换横排');
}

function renderCandidates() {
    const container = $('creationResult');
    if (!container) return;
    const poem = currentPoem();
    let html = '';
    if (state.candidates.length > 1) {
        html += '<div class="candidate-bar">';
        state.candidates.forEach((_, index) => {
            html += `<button class="${index === state.candidateIndex ? 'active' : ''}" data-index="${index}">候选 ${index + 1}</button>`;
        });
        html += '</div>';
    }
    html += `<div class="poem-text">${esc(poem) || '<span class="muted">暂无内容</span>'}</div>`;
    container.innerHTML = html;
    container.classList.toggle('vertical-poem', state.vertical);
    container.querySelectorAll('.candidate-bar button').forEach((button) => {
        button.onclick = () => {
            state.candidateIndex = Number(button.dataset.index) || 0;
            renderCandidates();
        };
    });
}

async function doCreation() {
    const genre = $('creationGenre') ? $('creationGenre').value : '五言绝句';
    const topicInput = $('creationTopic');
    let topic = topicInput ? topicInput.value.trim() : '';
    if (!topic) {
        topic = await guarded('获取随机主题', () => callApi('get_random_topic'), { toastError: false }) || '秋夜';
        if (topicInput) topicInput.value = topic;
    }
    state.genre = genre;
    state.topic = topic;

    const button = $('doCreationBtn');
    if (button) {
        button.disabled = true;
        button.textContent = '生成中...';
    }
    showLoading('creationResult', 'AI 创作中，请稍候...');
    try {
        const results = await withTimeout(callApi('generate', genre, topic, selectedStyle()), 90000, '创作');
        state.candidates = (Array.isArray(results) ? results : [results]).filter(Boolean);
        const usable = state.candidates.filter((text) => !/AI请求失败|API Key无效|生成失败/.test(text));
        if (!usable.length) {
            throw new Error(state.candidates[0] || '模型没有返回内容');
        }
        state.candidateIndex = 0;
        renderCandidates();
        showStatus(`已生成 ${state.candidates.length} 个候选`);
    } catch (error) {
        const container = $('creationResult');
        if (container) container.innerHTML = `<p class="error-text">生成失败：${esc(error.message || error)}</p>`;
        showToast(`生成失败：${error.message || error}`, 'error', 5000);
        const warning = $('apiWarning');
        if (warning) warning.classList.remove('hidden');
    } finally {
        hideLoading('creationResult');
        if (button) {
            button.disabled = false;
            button.textContent = '生成';
        }
    }
}

async function checkCreationPoem() {
    const poem = currentPoem();
    if (!poem) return showToast('请先生成作品', 'error');
    const genre = $('creationGenre') ? $('creationGenre').value : state.genre;
    const result = await guarded('格律检测', () => callApi('check_poem', poem, genre));
    if (result === null) return;
    alert(`格律检测结果：\n${Array.isArray(result) ? result.join('\n') : result}`);
}

async function saveCreation() {
    const poem = currentPoem();
    if (!poem) return showToast('请先生成作品', 'error');
    const genre = $('creationGenre') ? $('creationGenre').value : state.genre;
    const topicInput = $('creationTopic');
    const topic = topicInput && topicInput.value.trim() ? topicInput.value.trim() : state.topic || '未命名';
    await guarded('保存作品', () => callApi('save_work', genre, selectedStyle() || {}, topic, poem));
    showStatus('作品已保存到作品库');
    loadDashboard();
}

async function polishCreation() {
    const poem = currentPoem();
    if (!poem) return showToast('请先生成作品', 'error');
    showLoading('creationResult', '炼字分析中...');
    const result = await guarded('炼字', () => callApi('polish_line', poem), { toastError: false });
    hideLoading('creationResult');
    if (!result) return;
    if (result.error) return showToast(result.error, 'error', 4000);
    const suggestions = result.suggestions || [];
    if (!suggestions.length) return showToast('暂无炼字建议', 'info');
    let html = '<div class="suggestion-box"><h4>炼字建议</h4>';
    suggestions.forEach((item) => {
        html += `<p><b>${esc(item.original)}</b> → ${esc((item.replacements || []).join('、'))}<br><span class="muted">${esc(item.reason || '')}</span></p>`;
    });
    html += '</div>';
    if ($('creationResult')) $('creationResult').insertAdjacentHTML('beforeend', html);
}

async function transformCreation(target) {
    const poem = currentPoem();
    if (!poem) return showToast('请先生成作品', 'error');
    showLoading('creationResult', `正在改写为${target}...`);
    const result = await guarded('转体裁', () => callApi('transform_style', poem, target), { toastError: false });
    hideLoading('creationResult');
    if (!result) return;
    if (result.startsWith('AI请求失败') || result.includes('API Key无效')) {
        return showToast(result, 'error', 4200);
    }
    state.candidates[state.candidateIndex] = result;
    renderCandidates();
    showStatus(`已改写为${target}`);
}

async function continueMode() {
    const poem = currentPoem();
    if (!poem) return showToast('请先生成作品', 'error');
    const line = poem.split('\n').filter((item) => item.trim()).pop() || poem;
    const result = await guarded('续写', () => callApi('smart_continue', line), { timeout: 60000 });
    if (!Array.isArray(result)) return;
    let html = '<div class="suggestion-box"><h4>续写建议</h4>';
    result.forEach((item) => {
        html += `<div><b>${esc(item.direction)}</b><p>${esc(item.full_poem).replace(/\n/g, '<br>')}</p></div>`;
    });
    html += '</div>';
    if ($('creationResult')) $('creationResult').insertAdjacentHTML('beforeend', html);
}

async function critiqueWork() {
    const poem = currentPoem();
    if (!poem) return showToast('请先生成作品', 'error');
    const result = await guarded('品评', () => callApi('critique', poem, state.genre), { timeout: 60000 });
    if (!result) return;
    if ($('creationResult')) {
        $('creationResult').insertAdjacentHTML(
            'beforeend',
            `<div class="suggestion-box"><h4>品评</h4>${esc(result).replace(/\n/g, '<br>')}</div>`
        );
    }
}

function copyCurrent() {
    const poem = currentPoem();
    if (!poem) return showToast('请先生成作品', 'error');
    copyText(poem);
}

/* ---------------- 导出 ---------------- */
async function exportTxt() {
    const poem = currentPoem();
    if (!poem) return showToast('请先生成作品', 'error');
    const path = await guarded('导出TXT', () => callApi('export_txt', poem));
    if (path) showToast(`已导出：${path}`, 'success', 5000);
}

async function exportImage() {
    const poem = currentPoem();
    if (!poem) return showToast('请先生成作品', 'error');
    const style = selectedStyle() || {};
    const path = await guarded('导出图片', () => callApi('export_image_api', poem, 24, [255, 250, 240], style.poet || '心语'));
    if (path) showToast(`图片已导出：${path}`, 'success', 5000);
}

async function exportLetter() {
    const poem = currentPoem();
    if (!poem) return showToast('请先生成作品', 'error');
    const style = selectedStyle() || {};
    const path = await guarded('导出信笺', () => callApi('export_letter', poem, style.poet || '心语', '心语'));
    if (path) showToast(`信笺已导出：${path}`, 'success', 5000);
}

/* ---------------- 赏析 ---------------- */
async function doAppreciation() {
    const input = $('appreciationTitle');
    const title = input ? input.value.trim() : '';
    if (!title) return showToast('请输入作品名或诗句', 'error');
    const container = $('appreciationResult');
    if (!container) return;
    container.innerHTML = '';
    showLoading('appreciationResult', 'AI 赏析生成中...');
    try {
        const rows = await withTimeout(callApi('search_classics_v2', title, '', '', '', 1), 8000, '检索');
        let data = null;
        let header = '';
        if (rows && rows.length) {
            data = await withTimeout(callApi('deep_analysis', rows[0].id), 25000, '赏析');
            header = `《${rows[0].title}》 ${rows[0].author}`;
            callApi('record_classic_read', rows[0].id).catch(() => {});
        } else {
            data = await withTimeout(callApi('analyze_any_text', title), 25000, '赏析');
            header = `赏析：${title}`;
        }
        if (!data || data.error) {
            container.innerHTML = `<p class="error-text">${esc((data && data.error) || '赏析失败，请检查 API 设置')}</p>`;
            return;
        }
        const fields = [
            ['背景', data.background], ['解读', data.text_analysis], ['意境', data.artistic],
            ['格律', data.rhythm], ['文化', data.culture], ['教学', data.teaching],
        ];
        let html = `<h3>${esc(header)}</h3>`;
        fields.forEach(([label, value]) => {
            html += `<div class="analysis-row"><h4>${label}</h4><p>${esc(value || '暂无')}</p></div>`;
        });
        container.innerHTML = html;
    } catch (error) {
        container.innerHTML = `<p class="error-text">赏析失败：${esc(error.message || error)}</p>`;
    } finally {
        hideLoading('appreciationResult');
    }
}

async function getRandomClassic() {
    const item = await guarded('随机经典', () => callApi('get_random_classic'));
    if (!item) return;
    if ($('appreciationTitle')) $('appreciationTitle').value = item.title;
    switchNav('appreciation');
    doAppreciation();
}

/* ---------------- 教学 ---------------- */
async function loadTeachCats() {
    const select = $('teachCatSelect');
    if (!select) return;
    const categories = await guarded('加载分类', () => callApi('get_classic_categories_v2'), { toastError: false });
    select.innerHTML = '<option value="">全部</option>';
    if (!Array.isArray(categories)) return;
    categories.forEach((category) => {
        const option = document.createElement('option');
        option.value = category.category;
        option.textContent = `${category.category}（${category.count}）`;
        select.appendChild(option);
    });
    loadTeachArticles();
}

async function loadTeachArticles() {
    const categorySelect = $('teachCatSelect');
    const articleSelect = $('teachArtSelect');
    if (!categorySelect || !articleSelect) return;
    const rows = await guarded('加载文章', () => callApi('search_classics_v2', '', categorySelect.value, '', '', 200), { toastError: false });
    articleSelect.innerHTML = '';
    if (!Array.isArray(rows) || !rows.length) {
        articleSelect.innerHTML = '<option value="">暂无文章</option>';
        return;
    }
    rows.forEach((row) => {
        const option = document.createElement('option');
        option.value = row.id;
        option.textContent = `${row.title} - ${row.author}`;
        articleSelect.appendChild(option);
    });
    const preferred = rows.find((row) => row.is_famous && row.char_count <= 160 && ['唐诗', '宋词', '诗经', '楚辞'].includes(row.category))
        || rows.find((row) => row.is_famous && ['唐诗', '宋词', '诗经', '楚辞', '经典散文', '魏晋南北朝'].includes(row.category))
        || rows.find((row) => row.is_famous) || rows[0];
    let chosenId = preferred ? preferred.id : '';
    if (!preferred || preferred.char_count > 200) {
        try {
            const poems = await callApi('search_classics_v2', '', '唐诗', '', '', 1000);
            const knownTitles = ['静夜思', '春晓', '登鹳雀楼', '望庐山瀑布', '相思', '鹿柴'];
            const shortPoem = Array.isArray(poems)
                ? (poems.find((row) => knownTitles.includes(row.title))
                    || poems.filter((row) => row.is_famous).sort((a, b) => (a.char_count || 0) - (b.char_count || 0))[0]
                    || poems[0])
                : null;
            if (shortPoem && shortPoem.id) {
                let option = Array.from(articleSelect.options).find((item) => item.value === shortPoem.id);
                if (!option) {
                    option = document.createElement('option');
                    option.value = shortPoem.id;
                    option.textContent = `${shortPoem.title} - ${shortPoem.author}`;
                    articleSelect.appendChild(option);
                }
                chosenId = shortPoem.id;
            }
        } catch (error) {
            /* 保留默认选项 */
        }
    }
    if (chosenId) articleSelect.value = chosenId;
    articleSelect.onchange = () => loadCachedTeaching();
    if ($('teachLevel')) $('teachLevel').onchange = () => loadCachedTeaching();
    loadCachedTeaching();
}

function teachingProfile() {
    const get = (id, fallback) => ($(id) ? $(id).value : fallback);
    const stage = get('teachStage', 'junior');
    const hours = get('teachHours', '1');
    const textbook = get('teachTextbook', '部编版');
    const student = get('teachStudentLevel', '普通');
    if (stage === 'junior' && hours === '1' && textbook === '部编版' && student === '普通') return '';
    return `stage:${stage}|hours:${hours}|textbook:${textbook}|student:${student}`;
}

async function loadCachedTeaching() {
    const select = $('teachArtSelect');
    if (!select || !select.value) return;
    const level = $('teachLevel') ? $('teachLevel').value : 'standard';
    const result = await guarded('读取教案', () => callApi('get_teaching_plan', select.value, level, teachingProfile()), { toastError: false });
    if (result && result.available && result.plan) {
        renderTeachingPlan(result.plan);
        if ($('teachProgress')) $('teachProgress').textContent = '已加载预置/缓存教案';
    }
}

async function startTeaching(force = false) {
    const select = $('teachArtSelect');
    const id = select ? select.value : '';
    if (!id) return showToast('请选择作品', 'error');
    const level = $('teachLevel') ? $('teachLevel').value : 'standard';
    const profile = teachingProfile();
    if (!force) {
        const cached = await guarded('读取教案', () => callApi('get_teaching_plan', id, level, profile), { toastError: false });
        if (cached && cached.available && cached.plan) {
            renderTeachingPlan(cached.plan);
            showToast('使用预置/缓存教案，无需重新调用 AI', 'success', 2500);
            return;
        }
    }
    showLoading('tab-teaching', force ? '重新生成教案...' : '备课中（可用离线兜底）...');
    let data = null;
    try {
        data = await runJob(
            'teaching',
            { classic_id: id, level, profile, force: !!force },
            {
                timeout: 180000,
                onProgress: (job) => {
                    if ($('teachProgress')) {
                        $('teachProgress').textContent = `${Math.round(job.progress)}% ${job.message || ''}`;
                    }
                },
            }
        );
    } catch (error) {
        showToast(`教学加载失败：${error.message || error}`, 'error', 5000);
        return;
    } finally {
        hideLoading('tab-teaching');
    }
    if (!data) return showToast('教学加载失败，请检查网络或 API 余额', 'error', 5000);
    if (data.error) return showToast(data.error, 'error');
    renderTeachingPlan(data);
}

function teachingLinesHtml(lines) {
    let html = '<h4>逐句精讲</h4>';
    if (!lines.length) return html + '<p class="muted">暂无</p>';
    const notes = (state.wordNotes || []).slice().sort((a, b) => (b.term || '').length - (a.term || '').length);
    lines.forEach((line) => {
        const detail = [line.keywords && `关键词：${line.keywords}`, line.rhetoric && `修辞：${line.rhetoric}`, line.structure && `结构：${line.structure}`]
            .filter(Boolean).join('　');
        html += `<div class="teaching-line"><b>${decorateLine(line.original || '', notes)}</b>
            <span class="line-translation">${esc(line.translation || '译文待补充')}</span>
            ${detail ? `<small class="line-detail muted">${esc(detail)}</small>` : ''}</div>`;
    });
    return html;
}

function decorateLine(text, notes) {
    let html = esc(text);
    notes.forEach((item) => {
        if (!item.term) return;
        const term = esc(item.term);
        if (!html.includes(term) || html.includes(`data-term="${term}"`)) return;
        const replacement = `<span class="word-note" data-term="${term}" data-note="${esc(item.note || '')}" data-source="${esc(item.source || '')}">${term}</span>`;
        html = html.split(term).join(replacement);
    });
    return html;
}

async function loadWordNotes() {
    if (state.wordNotes) return;
    const data = await guarded('加载点注', () => callApi('get_word_notes'), { toastError: false });
    if (!data) return;
    const notes = Array.isArray(data.words) ? data.words.slice() : [];
    (data.allusions || []).forEach((item) => {
        (item.keywords || []).forEach((term) => notes.push({
            term, note: `典故：${item.name}。出处：${item.source || '待考'}`, source: '典故',
        }));
    });
    state.wordNotes = notes;
    state.wordAllusions = data.allusions || [];
    if (state.teaching) {
        const lines = (state.teaching.line_teaching && state.teaching.line_teaching.lines) || [];
        if ($('teachLines')) $('teachLines').innerHTML = teachingLinesHtml(lines);
    }
}

function showWordTip(target) {
    const tip = $('wordTip');
    if (!tip || !target) return;
    const note = target.dataset.note || '暂无注释';
    const source = target.dataset.source ? `<br><small>${esc(target.dataset.source)}</small>` : '';
    tip.innerHTML = `<b>${esc(target.dataset.term || '')}</b>：${esc(note)}${source}`;
    const rect = target.getBoundingClientRect();
    tip.style.left = `${Math.max(12, rect.left)}px`;
    tip.style.top = `${rect.bottom + 8}px`;
    tip.classList.remove('hidden');
}

function applyTeachingLayer() {
    const layer = $('teachLayer') ? $('teachLayer').value : 'compare';
    document.body.classList.remove('teach-layer-read', 'teach-layer-compare', 'teach-layer-full');
    document.body.classList.add(`teach-layer-${layer}`);
}

async function loadIntertext(data) {
    const cid = (data && data.id) || ($('teachArtSelect') ? $('teachArtSelect').value : '');
    if (!cid) return;
    const links = await guarded('加载互文', () => callApi('get_intertext', cid), { toastError: false });
    state.intertext = Array.isArray(links) ? links : [];
    if ($('teachIntertext')) {
        if (!state.intertext.length) {
            $('teachIntertext').innerHTML = '';
            return;
        }
        $('teachIntertext').innerHTML = '<h4>互文网络</h4>' + state.intertext.map((item) =>
            `<div class="teaching-line"><b>${esc(item.title || '')}</b> <span>${esc(item.author || '')}</span><small class="muted">${esc(item.relation || '')}${item.reason ? ' · ' + esc(item.reason) : ''}</small></div>`
        ).join('');
    }
}

function renderTeachingPlan(data) {
    if (!data) return;
    state.teaching = data;
    const analysis = data.analysis || {};
    const sourceMap = { prebuilt: '预置教案', 'offline-prebuilt': '离线预置', offline: '离线教案', ai: 'AI 生成', teacher: '我的版本', cache: '缓存' };
    const source = sourceMap[data._source || data.source] || '教案';
    if ($('teachMeta')) {
        $('teachMeta').innerHTML = `<b>《${esc(data.title || '')}》</b> · ${esc(data.author || '')} · ${esc(data.dynasty || '')} · ${esc(data.category || '')} <span class="chip static">${source}</span>${data.profile ? `<span class="chip static teacher-only">${esc(data.profile)}</span>` : ''}`;
    }
    const objectives = data.objectives || [];
    if ($('teachObjectives')) {
        $('teachObjectives').innerHTML = `<h4>教学目标</h4>${objectives.length
            ? `<ol>${objectives.map((item) => `<li>${esc(item)}</li>`).join('')}</ol>`
            : '<p class="muted">暂无</p>'}`;
    }
    const keyPoints = data.key_points || [];
    if ($('teachKeyPoints')) {
        $('teachKeyPoints').innerHTML = `<h4>重点提示</h4>${keyPoints.length
            ? `<ul>${keyPoints.map((item) => `<li>${esc(item)}</li>`).join('')}</ul>`
            : '<p class="muted">暂无</p>'}`;
    }
    if ($('teachBackground')) {
        $('teachBackground').innerHTML = `<h4>背景溯源</h4><p>${esc(analysis.background || '暂无')}</p>`;
    }
    const lines = (data.line_teaching && data.line_teaching.lines) || [];
    if ($('teachLines')) $('teachLines').innerHTML = teachingLinesHtml(lines);
    if ($('teachLines')) $('teachLines').onclick = (event) => {
        const target = event.target.closest('.word-note');
        if (target) showWordTip(target);
    };
    applyTeachingLayer();
    loadWordNotes();
    loadIntertext(data);

    let analysisHtml = `<h4>赏析</h4><p>${esc(analysis.text_analysis || '暂无')}</p>`;
    const extras = [['意境', analysis.artistic], ['格律', analysis.rhythm], ['文化', analysis.culture], ['教学建议', analysis.teaching]];
    extras.forEach(([label, value]) => {
        if (value) analysisHtml += `<div class="analysis-row"><h4>${label}</h4><p>${esc(value)}</p></div>`;
    });
    const related = data.related_works || [];
    if (related.length) {
        analysisHtml += '<h4>相关作品</h4><ul>';
        related.forEach((item) => {
            analysisHtml += `<li>${esc(item.title)} - ${esc(item.author)}</li>`;
        });
        analysisHtml += '</ul>';
    }
    if ($('teachAnalysis')) $('teachAnalysis').innerHTML = analysisHtml;

    const exercises = (data.exercises && data.exercises.exercises) || [];
    let exerciseHtml = '<h4>课堂练习</h4>';
    if (exercises.length) {
        exercises.forEach((exercise, index) => {
            exerciseHtml += `<div class="quiz-question"><b>${index + 1}. [${esc(exercise.type || '题')}]</b> ${esc(exercise.question)}`;
            if (Array.isArray(exercise.options) && exercise.options.length) {
                exerciseHtml += `<br><span class="muted">${exercise.options.map((option) => esc(option)).join('　')}</span>`;
            }
            exerciseHtml += `<br><span class="answer-text">答案：${esc(exercise.answer)}　解析：${esc(exercise.explanation || '')}</span></div>`;
        });
    } else {
        exerciseHtml += '<p class="muted">暂无</p>';
    }
    if ($('teachExercises')) $('teachExercises').innerHTML = exerciseHtml;

    let homeworkHtml = '';
    if (data.homework) homeworkHtml += `<h4>课后作业</h4><p>${esc(data.homework)}</p>`;
    if (data.board_design) homeworkHtml += `<h4>板书设计</h4><pre class="legal-text">${esc(data.board_design)}</pre>`;
    if ($('teachHomework')) $('teachHomework').innerHTML = homeworkHtml;

    markAsLearned($('teachArtSelect') ? $('teachArtSelect').value : '');
    renderNotes($('teachArtSelect') ? $('teachArtSelect').value : '');
}

function regenerateTeachingPlan() {
    startTeaching(true);
}

function downloadMarkdown(name, text) {
    const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function worksheetText(data) {
    const lines = (data.line_teaching && data.line_teaching.lines) || [];
    const exercises = (data.exercises && data.exercises.exercises) || [];
    let text = `# 《${data.title || ''}》学习单\n\n作者：${data.author || ''}　朝代：${data.dynasty || ''}\n\n`;
    text += `## 一、预习单\n\n1. 朗读三遍，标出停顿与易读错的字。\n2. 圈出三个不懂的词，查注释后写下来。\n3. 写下你读不懂的一个问题：\n\n`;
    text += `## 二、课堂任务单\n\n`;
    (data.objectives || []).forEach((item) => { text += `- ${item}\n`; });
    text += `\n原文：\n${data.content || ''}\n\n`;
    lines.forEach((line, index) => { text += `${index + 1}. ${line.original}\n   我的理解：____________________\n`; });
    text += `\n小组讨论：这首诗/文中最关键的动词或意象是什么？为什么？\n\n`;
    text += `## 三、课后作业单\n\n${data.homework || ''}\n\n`;
    exercises.forEach((exercise, index) => { text += `${index + 1}. ${exercise.question}\n`; });
    return text;
}

function exportWorksheets() {
    const data = state.teaching;
    if (!data) return showToast('请先生成教案', 'error');
    downloadMarkdown(`${data.title || '学习单'}-三单.md`, worksheetText(data));
    showToast('三单已导出', 'success');
}

function printWorksheets() {
    const data = state.teaching;
    if (!data) return showToast('请先生成教案', 'error');
    document.querySelectorAll('#printRoot').forEach((node) => node.remove());
    const root = document.createElement('div');
    root.id = 'printRoot';
    root.innerHTML = `<div class="print-sheet"><h1>《${esc(data.title || '')}》学习单</h1>
        <p>作者：${esc(data.author || '')}　朝代：${esc(data.dynasty || '')}</p>
        <h2>一、预习单</h2>
        <ol><li>朗读三遍，标出停顿与易读错的字。</li><li>圈出三个不懂的词，查注释后写下来。</li><li>写下你读不懂的一个问题。</li></ol>
        <h2>二、课堂任务单</h2>
        <p>${(data.objectives || []).map((item) => '· ' + esc(item)).join('<br>')}</p>
        <pre class="print-original">${esc(data.content || '')}</pre>
        <p>小组讨论：最关键的一个动词或意象是什么？为什么？</p>
        <h2>三、课后作业单</h2>
        <p>${esc(data.homework || '')}</p>
        </div>`;
    document.body.appendChild(root);
    document.body.classList.add('printing');
    const cleanup = () => {
        document.body.classList.remove('printing');
        root.remove();
    };
    window.addEventListener('afterprint', cleanup, { once: true });
    setTimeout(() => {
        window.print();
        setTimeout(cleanup, 1500);
    }, 100);
}

function openTeachingEditor() {
    const data = state.teaching;
    if (!data) return showToast('请先生成教案', 'error');
    const set = (id, value) => { if ($(id)) $(id).value = value || ''; };
    set('editObjectives', (data.objectives || []).join('\n'));
    set('editKeyPoints', (data.key_points || []).join('\n'));
    set('editBackground', (data.analysis && data.analysis.background) || '');
    set('editTextAnalysis', (data.analysis && data.analysis.text_analysis) || '');
    set('editTeaching', (data.analysis && data.analysis.teaching) || '');
    set('editHomework', data.homework || '');
    set('editBoard', data.board_design || '');
    if ($('teachEditor')) $('teachEditor').classList.remove('hidden');
}

function closeTeachingEditor() {
    if ($('teachEditor')) $('teachEditor').classList.add('hidden');
}

async function saveTeachingEditor() {
    const data = state.teaching;
    if (!data) return;
    const fields = {
        objectives: ($('editObjectives') ? $('editObjectives').value : '').split('\n').map((x) => x.trim()).filter(Boolean),
        key_points: ($('editKeyPoints') ? $('editKeyPoints').value : '').split('\n').map((x) => x.trim()).filter(Boolean),
        background: $('editBackground') ? $('editBackground').value.trim() : '',
        text_analysis: $('editTextAnalysis') ? $('editTextAnalysis').value.trim() : '',
        teaching: $('editTeaching') ? $('editTeaching').value.trim() : '',
        homework: $('editHomework') ? $('editHomework').value.trim() : '',
        board_design: $('editBoard') ? $('editBoard').value.trim() : '',
    };
    const id = $('teachArtSelect') ? $('teachArtSelect').value : '';
    const level = $('teachLevel') ? $('teachLevel').value : 'standard';
    const result = await guarded('保存教案', () => callApi('save_teaching_plan_custom', id, level, teachingProfile(), JSON.stringify(fields)));
    if (result && result.available) {
        renderTeachingPlan(result.plan);
        closeTeachingEditor();
        showToast('已保存为我的版本', 'success');
    }
}

async function restoreTeachingPlan() {
    const id = $('teachArtSelect') ? $('teachArtSelect').value : '';
    const level = $('teachLevel') ? $('teachLevel').value : 'standard';
    const result = await guarded('恢复预置', () => callApi('restore_teaching_plan', id, level, teachingProfile()));
    if (result && result.available) {
        renderTeachingPlan(result.plan);
        closeTeachingEditor();
        showToast('已恢复预置教案', 'success');
    }
}

function toggleClassroomMode() {
    document.body.classList.remove('student-mode');
    document.body.classList.toggle('classroom-mode');
    if (document.body.classList.contains('classroom-mode')) {
        switchNav('teaching');
        showToast('课堂模式：答案已隐藏，按 Esc 退出', 'success', 2500);
    }
}

function toggleStudentMode() {
    document.body.classList.remove('classroom-mode');
    document.body.classList.toggle('student-mode');
    if (document.body.classList.contains('student-mode')) {
        switchNav('teaching');
        showToast('学生模式：已隐藏答案与教师备注', 'success', 2500);
    }
}

function exitClassroomModes() {
    document.body.classList.remove('classroom-mode', 'student-mode');
    showToast('已退出课堂模式', 'success');
}

function exportTeachingPlan() {
    const data = state.teaching;
    if (!data) return showToast('请先生成教案', 'error');
    const lines = (data.line_teaching && data.line_teaching.lines) || [];
    const exercises = (data.exercises && data.exercises.exercises) || [];
    let text = `# 《${data.title || ''}》教案\n\n作者：${data.author || ''}　朝代：${data.dynasty || ''}\n\n## 教学目标\n`;
    (data.objectives || []).forEach((item) => { text += `- ${item}\n`; });
    text += `\n## 重点\n`; (data.key_points || []).forEach((item) => { text += `- ${item}\n`; });
    text += `\n## 背景\n${(data.analysis && data.analysis.background) || ''}\n`;
    text += `\n## 逐句\n`;
    lines.forEach((line) => { text += `- ${line.original}：${line.translation || '（待补充）'}\n`; });
    text += `\n## 练习\n`;
    exercises.forEach((exercise, index) => { text += `${index + 1}. ${exercise.question}（答案：${exercise.answer}）\n`; });
    text += `\n## 作业\n${data.homework || ''}\n`;
    downloadMarkdown(`${data.title || '教案'}-教案.md`, text);
    showToast('教案已导出', 'success');
}

function updateTeachProgress() {
    const label = $('teachProgress');
    if (label) label.textContent = `已学习 ${state.learned.length} 篇`;
}

function markAsLearned(id) {
    if (!id || state.learned.includes(id)) return;
    state.learned.push(id);
    safeSet('learnedWorks', state.learned);
    persistUiState({ learned: state.learned });
    updateTeachProgress();
}

async function saveNote() {
    const select = $('teachArtSelect');
    const input = $('noteInput');
    if (!select || !select.value) return showToast('请先选择作品', 'error');
    const text = input ? input.value.trim() : '';
    if (!text) return showToast('笔记内容不能为空', 'error');
    const result = await guarded('保存笔记', () => callApi('save_note', select.value, text));
    if (result) {
        if (input) input.value = '';
        showToast('笔记已保存', 'success');
        renderNotes(select.value);
    }
}

async function renderNotes(workId) {
    const container = $('noteList');
    if (!container) return;
    if (!workId) {
        container.innerHTML = '<p class="muted">选择作品后可查看笔记</p>';
        return;
    }
    const notes = await guarded('加载笔记', () => callApi('get_notes', workId), { toastError: false });
    if (!Array.isArray(notes) || !notes.length) {
        container.innerHTML = '<p class="muted">暂无笔记</p>';
        return;
    }
    container.innerHTML = notes
        .map((note) => `<div class="note-item">${esc(note.note_text)}<br><span class="muted">${esc(note.created_at || '')}</span></div>`)
        .join('');
}

/* ---------------- 题库 ---------------- */
async function startQuiz() {
    const category = $('quizCat') ? $('quizCat').value : '唐诗';
    const difficulty = parseInt(($('quizDifficulty') || {}).value, 10) || 1;
    const count = parseInt(($('quizCount') || {}).value, 10) || 5;
    const blueprint = ($('quizBlueprint') || {}).value || 'basic';
    const select = $('quizTypes');
    const types = select
        ? Array.from(select.selectedOptions).map((option) => option.value).join(',') || '选择'
        : '选择';
    const container = $('quizContent');
    if (!container) return;
    container.innerHTML = '<p class="muted">正在生成题目...</p>';
    showLoading('quizContent', '组卷中...');
    const result = await guarded('生成试卷', () => callApi('generate_quiz', category, difficulty, count, types, blueprint), { toastError: false });
    hideLoading('quizContent');
    if (!result || !Array.isArray(result.questions) || !result.questions.length) {
        container.innerHTML = '<p class="error-text">未能生成题目，请更换分类后重试。</p>';
        return;
    }
    state.quiz = result;
    const sourceText = result.source === 'bank+rubric' ? '本地题库 + Rubric'
        : (result.source === 'bank' ? '本地题库' : 'AI/规则');
    let html = `<div class="result-meta">组卷来源：${sourceText} · ${result.questions.length} 题</div>`;
    result.questions.forEach((question, index) => {
        html += `<div class="quiz-question"><p><b>${index + 1}. [${esc(question.type)}]</b> ${esc(question.question)}</p>`;
        if (question.type === '选择') {
            (question.options || []).forEach((option, optionIndex) => {
                html += `<label><input type="radio" name="q${index}" value="${optionIndex}"> ${esc(option)}</label>`;
            });
        } else if (question.type === '判断') {
            html += `<label><input type="radio" name="q${index}" value="0"> 正确</label> `;
            html += `<label><input type="radio" name="q${index}" value="1"> 错误</label> `;
        } else {
            html += `<input type="text" name="q${index}" placeholder="填写答案">`;
        }
        html += '</div>';
    });
    html += '<button class="primary-btn" id="submitQuizBtn">提交答案</button>';
    container.innerHTML = html;
    if ($('submitQuizBtn')) $('submitQuizBtn').onclick = submitQuiz;
    if ($('quizProgress')) $('quizProgress').textContent = `共 ${result.questions.length} 题`;
    if ($('quizScore')) $('quizScore').textContent = '';
}

function collectAnswers() {
    if (!state.quiz) return [];
    return state.quiz.questions.map((question, index) => {
        if (question.type === '选择' || question.type === '判断') {
            const selected = document.querySelector(`input[name="q${index}"]:checked`);
            return selected ? parseInt(selected.value, 10) : -1;
        }
        const input = document.querySelector(`input[name="q${index}"]`);
        return input ? input.value.trim() : '';
    });
}

async function submitQuiz() {
    if (!state.quiz) return showToast('请先生成试卷', 'error');
    const answers = collectAnswers();
    const result = await guarded('批改', () => callApi('check_quiz_answer', JSON.stringify(state.quiz), JSON.stringify(answers)));
    if (!result) return;
    if ($('quizScore')) {
        const pendingText = Array.isArray(result.pending) && result.pending.length ? `，开放题 ${result.pending.length} 道待评分` : '';
        $('quizScore').textContent = `客观题得分：${result.score} 分（${result.correct}/${result.auto_total || 0}）${pendingText}`;
    }
    if (Array.isArray(result.wrong) && result.wrong.length) {
        let html = '<h4>错题解析</h4>';
        result.wrong.forEach((wrong) => {
            const question = state.quiz.questions[wrong.index] || {};
            html += `<p>第 ${wrong.index + 1} 题：${esc(wrong.explanation || question.explanation || '')}<br><span class="muted">正确答案：${esc(wrong.correct)}</span></p>`;
            const answer = answers[wrong.index];
            const options = Array.isArray(question.options) ? question.options : [];
            const yourAnswer = question.type === '选择' || question.type === '判断'
                ? options[Number(answer)] || '未选' : answer || '未填';
            const correctAnswer = question.type === '选择' || question.type === '判断'
                ? options[Number(question.answer)] || wrong.correct : wrong.correct;
            state.wrongBook.push({
                type: question.type || '题目',
                question: question.question || '',
                options, yourAnswer, correctAnswer,
                explanation: wrong.explanation || question.explanation || '',
            });
        });
        safeSet('wrongBook', state.wrongBook.slice(-100));
        persistUiState({ wrong_book: state.wrongBook.slice(-100) });
        if ($('quizContent')) $('quizContent').insertAdjacentHTML('beforeend', html);
    }
    if (Array.isArray(result.pending) && result.pending.length) {
        let html = '<h4>开放题：待教师按量规评分</h4>';
        result.pending.forEach((item) => {
            html += `<div class="quiz-question"><b>第 ${item.index + 1} 题</b> ${esc(item.question || '')}`;
            (item.rubric || []).forEach((rubric) => {
                html += `<br><span class="muted">${esc(rubric.dimension)}（${rubric.points} 分）：${esc(rubric.criteria)}</span>`;
            });
            html += `<br><span class="muted">参考思路：${esc(item.answer_hint || '')}</span></div>`;
        });
        if ($('quizContent')) $('quizContent').insertAdjacentHTML('beforeend', html);
    }
    const history = safeGet('quizHistory', []);
    history.unshift({ score: result.score, total: result.total, time: new Date().toLocaleString() });
    safeSet('quizHistory', history.slice(0, 20));
    persistUiState({ quiz_history: history.slice(0, 20) });
    if (state.timer) {
        clearInterval(state.timer);
        state.timer = null;
    }
}

function startTimedQuiz() {
    startQuiz().then(() => {
        if (!state.quiz) return;
        state.timeLeft = 60;
        if ($('quizProgress')) $('quizProgress').textContent = '剩余 60 秒';
        clearInterval(state.timer);
        state.timer = setInterval(() => {
            state.timeLeft -= 1;
            if ($('quizProgress')) $('quizProgress').textContent = `剩余 ${state.timeLeft} 秒`;
            if (state.timeLeft <= 0) {
                clearInterval(state.timer);
                state.timer = null;
                alert('时间到，自动提交');
                submitQuiz();
            }
        }, 1000);
    });
}

function openWrongBook() {
    state.wrongBook = loadUiList('wrong_book', 'wrongBook', []);
    const container = $('quizContent');
    if (!container) return;
    if (!state.wrongBook.length) {
        container.innerHTML = '<p class="muted">暂无错题，继续加油！</p>';
        return;
    }
    let html = '<h3>错题本</h3>';
    state.wrongBook.forEach((item, index) => {
        html += `<div class="quiz-question"><b>${index + 1}. [${esc(item.type)}]</b> ${esc(item.question)}`;
        html += `<br><span class="muted">你的答案：${esc(item.yourAnswer)}　正确答案：${esc(item.correctAnswer)}</span>`;
        html += `<br><span class="muted">解析：${esc(item.explanation || '')}</span></div>`;
    });
    html += '<button onclick="clearWrongBook()">清空错题本</button>';
    container.innerHTML = html;
}

function clearWrongBook() {
    if (!confirm('确定清空所有错题？')) return;
    state.wrongBook = [];
    safeSet('wrongBook', []);
    persistUiState({ wrong_book: [] });
    if ($('quizContent')) $('quizContent').innerHTML = '<p class="muted">错题本已清空</p>';
    showToast('错题本已清空', 'success');
}

function loadQuizHistory() {
    const history = loadUiList('quiz_history', 'quizHistory', []);
    const container = $('quizContent');
    if (!container) return;
    if (!history.length) {
        container.innerHTML = '<p class="muted">暂无历史记录</p>';
        return;
    }
    let html = '<h3>历史测验</h3>';
    history.forEach((item, index) => {
        html += `<p>第 ${index + 1} 次：${esc(item.score)} 分（${esc(item.total)} 题）<span class="muted"> ${esc(item.time || '')}</span></p>`;
    });
    container.innerHTML = html;
}

/* ---------------- 经典文库 ---------------- */
async function showClassicsCategories() {
    state.panelCat = '';
    state.panelKeyword = '';
    state.panelPage = 1;
    if ($('classicSearch')) $('classicSearch').value = '';
    const grid = $('classicsGrid');
    const pager = $('classicsPager');
    if (!grid) return;
    grid.innerHTML = '<p class="muted">加载分类...</p>';
    if (pager) pager.innerHTML = '';
    const categories = await guarded('加载分类', () => callApi('get_classic_categories_v2'), { toastError: false });
    grid.innerHTML = '';
    if (!Array.isArray(categories) || !categories.length) {
        grid.innerHTML = '<p class="muted">暂无分类数据</p>';
        return;
    }
    categories.forEach((category) => {
        const card = document.createElement('button');
        card.className = 'category-card';
        card.innerHTML = `<b>${esc(category.category)}</b><span>${category.count} 篇</span>`;
        card.onclick = () => openClassicsPanel(category.category);
        grid.appendChild(card);
    });
    state.panelTotal = categories.reduce((sum, item) => sum + item.count, 0);
}

async function openClassicsPanel(category, keyword = '') {
    if (!$('tab-classics') || !$('tab-classics').classList.contains('active')) {
        state.skipClassicsLoad = true;
        switchNav('classics');
    }
    state.panelCat = category || '';
    state.panelKeyword = keyword || '';
    state.panelPage = 1;
    if ($('classicSearch')) $('classicSearch').value = state.panelKeyword;
    await loadClassicsPage();
}

async function searchClassics() {
    const keyword = $('classicSearch') ? $('classicSearch').value.trim() : '';
    state.panelKeyword = keyword;
    state.panelPage = 1;
    await loadClassicsPage();
}

function toggleVerifiedOnly(checked) {
    state.verifiedOnly = !!checked;
    state.panelPage = 1;
    loadClassicsPage();
}

async function loadClassicsPage() {
    const grid = $('classicsGrid');
    if (!grid) return;
    grid.innerHTML = '<p class="muted">检索中...</p>';
    showLoading('classicsGrid', '检索中...');
    const result = await guarded('检索文库', () => callApi(
        'search_classics_page',
        state.panelKeyword,
        state.panelCat,
        '',
        '',
        state.panelPage,
        state.panelPageSize,
        state.verifiedOnly
    ), { toastError: false });
    hideLoading('classicsGrid');
    if (!result) {
        grid.innerHTML = '<p class="error-text">检索失败，请重试</p>';
        return;
    }
    state.panelItems = result.items || [];
    state.panelTotal = result.total || 0;
    state.panelPages = result.pages || 1;
    state.panelPage = result.page || 1;
    renderClassicsGrid();
}

function renderClassicsGrid() {
    const grid = $('classicsGrid');
    const pager = $('classicsPager');
    if (!grid) return;
    const title = state.panelKeyword
        ? `搜索「${esc(state.panelKeyword)}」`
        : (state.panelCat ? `${esc(state.panelCat)}` : '全部作品');
    let html = `<div class="result-meta">${title}${state.verifiedOnly ? ' · 只看已校勘' : ''} · 共 ${state.panelTotal} 篇</div>`;
    if (!state.panelItems.length) {
        html += '<p class="muted">没有找到作品，换个关键词试试。</p>';
        grid.innerHTML = html;
        if (pager) pager.innerHTML = '';
        return;
    }
    state.panelItems.forEach((item) => {
        const excerpt = String(item.content || '').replace(/\n/g, ' ').slice(0, 46);
        html += `<article class="classic-card" data-id="${esc(item.id)}">
            <header><b>${esc(item.title)}</b><span>${item.is_famous ? '名篇' : esc(item.category)}</span></header>
            <p class="muted">${esc(item.author)} · ${esc(item.dynasty)}</p>
            <p class="excerpt">${esc(excerpt)}${excerpt.length >= 46 ? '…' : ''}</p>
        </article>`;
    });
    grid.innerHTML = html;
    grid.querySelectorAll('.classic-card').forEach((card) => {
        card.onclick = () => showPanelDetail(card.dataset.id);
    });
    renderClassicsPager();
}

function renderClassicsPager() {
    const pager = $('classicsPager');
    if (!pager) return;
    const current = state.panelPage;
    const pages = state.panelPages;
    let html = '';
    html += `<button ${current <= 1 ? 'disabled' : ''} data-page="${current - 1}">上一页</button>`;
    const start = Math.max(1, current - 2);
    const end = Math.min(pages, start + 4);
    for (let page = start; page <= end; page += 1) {
        html += `<button class="${page === current ? 'active' : ''}" data-page="${page}">${page}</button>`;
    }
    html += `<button ${current >= pages ? 'disabled' : ''} data-page="${current + 1}">下一页</button>`;
    html += `<span class="muted">第 ${current} / ${pages} 页</span>`;
    pager.innerHTML = html;
    pager.querySelectorAll('button[data-page]').forEach((button) => {
        button.onclick = () => {
            const page = Number(button.dataset.page);
            if (page >= 1 && page <= pages && page !== current) {
                state.panelPage = page;
                loadClassicsPage();
            }
        };
    });
}

async function showFavorites() {
    state.skipClassicsLoad = true;
    switchNav('classics');
    state.panelCat = '';
    state.panelKeyword = '';
    const grid = $('classicsGrid');
    const pager = $('classicsPager');
    if (!grid) return;
    if (pager) pager.innerHTML = '';
    grid.innerHTML = '<p class="muted">加载收藏...</p>';
    const rows = await guarded('加载收藏', () => callApi('get_favorites'), { toastError: false });
    if (!Array.isArray(rows)) return;
    if (!rows.length) {
        grid.innerHTML = '<p class="muted">暂无收藏，去经典文库挑几篇吧。</p>';
        return;
    }
    grid.innerHTML = '';
    rows.forEach((row) => {
        const card = document.createElement('article');
        card.className = 'classic-card';
        card.innerHTML = `<header><b>${esc(row.title)}</b><span>收藏</span></header>
            <p class="muted">${esc(row.author)} · ${esc(row.dynasty)}</p>`;
        card.onclick = () => showPanelDetail(row.classic_id || row.id);
        grid.appendChild(card);
    });
}

/* ---------------- 详情与二创 ---------------- */
async function showPanelDetail(id) {
    const item = await guarded('读取作品', () => callApi('get_classic_by_id_v2', id));
    if (!item) return;
    callApi('record_classic_read', id).catch(() => {});
    const panel = $('classicsPanel');
    const overlay = $('classicsOverlay');
    if (panel) panel.classList.remove('hidden');
    if (overlay) overlay.classList.remove('hidden');
    const header = $('classicsHeader');
    if (header) header.querySelector('span').textContent = '经典详情';
    const container = $('classicsContent');
    if (!container) return;

    let html = `<h2 class="detail-title">《${esc(item.title)}》</h2>
        <p class="muted">${esc(item.author)} · ${esc(item.dynasty)} · ${esc(item.category)}${item.subcategory ? ' · ' + esc(item.subcategory) : ''}</p>`;
    if (item.verified) html += '<p><span class="chip static">已校勘</span><span class="chip static">传统经典</span></p>';
    html += `<div class="poem-text detail-poem" id="detailPoem">${esc(item.content)}</div>`;
    if (item.translation) {
        const draft = item.translation_status === 'draft';
        html += `<div class="analysis-row"><h4>译文${draft ? '（AI 草案，待复核）' : (item.translation_status === 'approved' ? '（已复核）' : '')}</h4><p>${esc(item.translation)}</p></div>`;
    }
    if (item.annotation) {
        const draft = item.annotation_status === 'draft';
        html += `<div class="analysis-row"><h4>注释${draft ? '（AI 草案，待复核）' : (item.annotation_status === 'approved' ? '（已复核）' : '')}</h4><p>${esc(item.annotation)}</p></div>`;
    }
    if (item.tags) html += `<p class="muted">标签：${esc(item.tags)}</p>`;

    html += `<div class="detail-actions">
        <button class="primary-btn" id="detailSpeak">朗读</button>
        <button id="detailDeep">六维赏析</button>
        <button id="detailQuality">质量评分</button>
        <button id="detailFav">收藏</button>
        <button id="detailCompare">对比</button>
        <button id="detailRhetoric">修辞</button>
        <button id="detailDelete">删除</button>
    </div>`;
    html += `<div class="detail-tools">
        <div class="tool-line">
            <label>二创</label>
            <select id="recreateMode">
                <option value="buyun">步韵</option>
                <option value="fangxie">仿写</option>
                <option value="fanxie">反写</option>
                <option value="kuoxie">扩写</option>
                <option value="suoxie">缩写</option>
                <option value="modern">现代文</option>
            </select>
            <input id="recreateExtra" placeholder="仿写主题（可选）">
            <button id="runRecreate">生成</button>
        </div>
        <div class="tool-line">
            <label>翻译</label>
            <select id="translateLang"><option value="en">英文</option><option value="ja">日文</option></select>
            <button id="runTranslate">翻译</button>
        </div>
    </div>`;
    html += `<div id="detailExtra" class="tab-content-sub"></div>`;
    html += `<div class="notes-block"><h4>我的笔记</h4>
        <div id="detailNotes" class="list-stack"><p class="muted">加载中...</p></div>
        <textarea id="detailNoteInput" placeholder="写一句批注..."></textarea>
        <button id="saveDetailNote">保存笔记</button></div>`;
    container.innerHTML = html;
    if ($('classicsPagination')) $('classicsPagination').innerHTML = '';

    $('detailSpeak').onclick = () => {
        state.speakContent = item.content || '';
        openSpeakPanel();
    };
    $('detailDeep').onclick = () => deepAnalysis(id);
    $('detailQuality').onclick = () => qualityCheck(id);
    $('detailFav').onclick = () => favoritePanelDetail(id);
    $('detailCompare').onclick = () => compareClassic(id);
    $('detailRhetoric').onclick = () => analyzeRhetoric(id, item.content);
    $('detailDelete').onclick = () => deleteClassic(id);
    $('runRecreate').onclick = () => runRecreate(id);
    $('runTranslate').onclick = () => runTranslate(id);
    $('saveDetailNote').onclick = () => addDetailNote(id);
    loadDetailNotes(id);
}

async function loadDetailNotes(id) {
    const container = $('detailNotes');
    if (!container) return;
    const notes = await guarded('加载笔记', () => callApi('get_notes', id), { toastError: false });
    if (!Array.isArray(notes) || !notes.length) {
        container.innerHTML = '<p class="muted">还没有笔记</p>';
        return;
    }
    container.innerHTML = notes.map((note) => `<div class="note-item">${esc(note.note_text)}<br><span class="muted">${esc(note.created_at || '')}</span></div>`).join('');
}

async function addDetailNote(id) {
    const input = $('detailNoteInput');
    const text = input ? input.value.trim() : '';
    if (!text) return showToast('笔记不能为空', 'error');
    const result = await guarded('保存笔记', () => callApi('save_note', id, text));
    if (result) {
        if (input) input.value = '';
        showToast('笔记已保存', 'success');
        loadDetailNotes(id);
    }
}

async function deepAnalysis(id) {
    const extra = $('detailExtra');
    if (extra) extra.innerHTML = '<p class="muted">AI 赏析中...</p>';
    const data = await guarded('深度赏析', () => callApi('deep_analysis', id), { timeout: 40000, toastError: false });
    if (!extra) return;
    if (!data || data.error) {
        extra.innerHTML = `<p class="error-text">${esc((data && data.error) || '赏析失败，请检查 API 设置')}</p>`;
        return;
    }
    const fields = [
        ['背景', data.background], ['文本解读', data.text_analysis], ['意境', data.artistic],
        ['格律', data.rhythm], ['文化', data.culture], ['教学', data.teaching],
    ];
    extra.innerHTML = fields.map(([label, value]) => `<div class="analysis-row"><h4>${label}</h4><p>${esc(value || '暂无')}</p></div>`).join('');
}

async function qualityCheck(id) {
    const data = await guarded('质量评分', () => callApi('quality_score', id));
    if (!data) return;
    if (data.error) return showToast(data.error, 'error');
    const extra = $('detailExtra');
    if (extra) {
        let html = `<h4>质量评分：${data.score} 分（${esc(data.grade)} 级 ${esc(data.stars)}）</h4><ul>`;
        Object.keys(data.details || {}).forEach((key) => {
            html += `<li>${esc(key)}：+${data.details[key]}</li>`;
        });
        html += '</ul>';
        extra.innerHTML = html;
    }
}

async function favoritePanelDetail(id) {
    await guarded('收藏', () => callApi('add_favorite', id));
    showToast('已加入收藏', 'success');
}

async function runRecreate(id) {
    const mode = $('recreateMode') ? $('recreateMode').value : 'buyun';
    const extra = $('recreateExtra') ? $('recreateExtra').value.trim() : '';
    const extraBox = $('detailExtra');
    if (extraBox) extraBox.innerHTML = '<p class="muted">二创生成中...</p>';
    const result = await guarded('二创', () => callApi('recreate_classic', id, mode, extra), { timeout: 60000, toastError: false });
    if (!extraBox) return;
    if (!result) {
        extraBox.innerHTML = '<p class="error-text">二创失败，请检查 API 设置</p>';
        return;
    }
    extraBox.innerHTML = `<div class="generated-block"><div class="generated-head"><h4>二创结果</h4>
        <button id="copyRecreate">复制</button></div>
        <div class="poem-text">${esc(result)}</div></div>`;
    if ($('copyRecreate')) $('copyRecreate').onclick = () => copyText(result);
}

async function runTranslate(id) {
    const lang = $('translateLang') ? $('translateLang').value : 'en';
    const extraBox = $('detailExtra');
    if (extraBox) extraBox.innerHTML = '<p class="muted">翻译中...</p>';
    const result = await guarded('翻译', () => callApi('recreate_classic', id, 'translate', lang), { timeout: 60000, toastError: false });
    if (!extraBox) return;
    if (!result) {
        extraBox.innerHTML = '<p class="error-text">翻译失败，请检查 API 设置</p>';
        return;
    }
    extraBox.innerHTML = `<div class="generated-block"><div class="generated-head"><h4>译文</h4>
        <button id="copyTranslate">复制</button></div>
        <div class="poem-text">${esc(result)}</div></div>`;
    if ($('copyTranslate')) $('copyTranslate').onclick = () => copyText(result);
}

async function analyzeRhetoric(id, content) {
    const extraBox = $('detailExtra');
    if (extraBox) extraBox.innerHTML = '<p class="muted">分析修辞...</p>';
    const data = await guarded('修辞分析', () => callApi('analyze_rhetoric', content), { toastError: false });
    if (!extraBox) return;
    if (!data) {
        extraBox.innerHTML = '<p class="error-text">分析失败</p>';
        return;
    }
    let html = '<h4>修辞分析</h4>';
    html += `<p><b>对仗：</b>${esc((data.antithesis || []).join('；') || '未发现明显对仗')}</p>`;
    html += `<p><b>典故：</b>${esc((data.allusions || []).join('；') || '未发现典故')}</p>`;
    html += `<p><b>叠字：</b>${esc((data.reduplication || []).join('、') || '无')}</p>`;
    extraBox.innerHTML = html;
}

async function compareClassic(id) {
    const answer = prompt('输入另一篇作品的标题，进行对比赏析：', '');
    if (!answer) return;
    const rows = await guarded('检索对比作品', () => callApi('search_classics_v2', answer, '', '', '', 1), { toastError: false });
    if (!rows || !rows.length) return showToast('没有找到对比作品', 'error');
    const extraBox = $('detailExtra');
    if (extraBox) extraBox.innerHTML = '<p class="muted">对比分析中...</p>';
    const result = await guarded('对比赏析', () => callApi('compare_classics', id, rows[0].id), { timeout: 60000, toastError: false });
    if (!extraBox) return;
    extraBox.innerHTML = `<div class="analysis-row"><h4>与《${esc(rows[0].title)}》对比</h4>
        <p>${esc(result || '对比失败')}</p></div>`;
}

function copyText(text) {
    const content = String(text || '');
    if (!content) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(content)
            .then(() => showToast('已复制', 'success'))
            .catch(() => fallbackCopy(content));
        return;
    }
    fallbackCopy(content);
}

function fallbackCopy(text) {
    try {
        const area = document.createElement('textarea');
        area.value = text;
        area.style.position = 'fixed';
        area.style.opacity = '0';
        document.body.appendChild(area);
        area.select();
        document.execCommand('copy');
        area.remove();
        showToast('已复制', 'success');
    } catch (error) {
        showToast('当前环境不支持剪贴板', 'error');
    }
}

async function deleteClassic(id) {
    if (!confirm('确定删除这篇作品？关联的笔记、收藏和阅读记录也会删除。')) return;
    const message = await guarded('删除', () => callApi('delete_classic', id));
    if (message) {
        showToast(message, 'success');
        closeClassicsPanel();
        loadClassicsPage();
        loadDashboard();
    }
}

function closeClassicsPanel() {
    if ($('classicsPanel')) $('classicsPanel').classList.add('hidden');
    if ($('classicsOverlay')) $('classicsOverlay').classList.add('hidden');
}

/* ---------------- 数据面板 ---------------- */
async function loadAiReview() {
    const panel = $('aiReviewPanel');
    if (!panel) return;
    const rows = await guarded('加载审核队列', () => callApi('get_ai_review_queue', 'pending'), { toastError: false });
    if (!Array.isArray(rows) || !rows.length) {
        panel.innerHTML = '<p class="muted">暂无待审核 AI 内容</p>';
        return;
    }
    panel.innerHTML = rows.map((row) => {
        const payload = row.payload || {};
        return `<div class="backup-row"><div><b>${esc(row.kind)}</b> · ${esc(payload.title || '')}<br>
            <span class="muted">${esc((payload.objectives || []).join(' / ')).slice(0, 120)}</span></div>
            <div class="action-row"><button onclick="reviewAiItem(${row.id},'approved')">通过</button>
            <button onclick="reviewAiItem(${row.id},'rejected')">拒绝</button></div></div>`;
    }).join('');
}

async function reviewAiItem(id, decision) {
    const result = await guarded('审核 AI 内容', () => callApi('review_ai_queue', String(id), decision, 'teacher', ''));
    if (result && result.success) {
        showToast(decision === 'approved' ? '已通过' : '已拒绝', 'success');
        loadAiReview();
    }
}

async function loadAiBudget() {
    const panel = $('budgetPanel');
    if (!panel) return;
    const data = await guarded('AI 预算', () => callApi('get_ai_budget'), { toastError: false });
    if (!data) {
        panel.innerHTML = '<p class="muted">暂时无法读取预算</p>';
        return;
    }
    const daily = Number(data.daily_budget || 0);
    const spent = Number(data.spent || 0);
    const remaining = data.remaining === null ? '不限' : `¥${Number(data.remaining || 0).toFixed(4)}`;
    const percent = daily > 0 ? Math.min(100, (spent / daily) * 100) : 0;
    panel.innerHTML = `<div class="mini-stats">
        <div><b>¥${spent.toFixed(4)}</b><span>今日已用</span></div>
        <div><b>${remaining}</b><span>今日剩余</span></div>
        <div><b>${data.calls || 0}</b><span>调用次数</span></div>
        <div><b>${daily ? '¥' + daily.toFixed(2) : '不限'}</b><span>每日预算</span></div>
    </div>
    <div class="progress-bar" style="margin-top:10px"><div class="progress-bar-fill" style="width:${percent}%"></div></div>
    <p class="muted">预算在 data/ai_budget.json；超限后 AI 调用会被拦截。</p>`;
}

async function loadUsageDashboard() {
    switchNav('data');
    const container = $('usageDashboard');
    if (container) container.innerHTML = '<p class="muted">加载中...</p>';
    const data = await guarded('加载用量', () => callApi('get_usage_dashboard'), { toastError: false });
    if (!container) return;
    if (!data) {
        container.innerHTML = '<p class="error-text">加载失败</p>';
        return;
    }
    let html = `<div class="mini-stats">
        <div><b>${fmtNumber(data.monthly_calls)}</b><span>本月调用</span></div>
        <div><b>${fmtNumber(data.monthly_tokens)}</b><span>本月 Token</span></div>
        <div><b>${fmtNumber(data.total_calls)}</b><span>累计调用</span></div>
        <div><b>¥${Number(data.total_cost || 0).toFixed(4)}</b><span>累计费用</span></div>
    </div>`;
    html += `<p class="muted">${esc(data.provider)} · ${esc(data.model)} · ${data.has_key ? 'Key 已配置' : '未配置 Key'}</p>`;
    html += '<h4>近 7 天</h4><div class="usage-bars">';
    (data.daily || []).slice(0, 7).reverse().forEach((day) => {
        const max = Math.max(...(data.daily || []).map((item) => item.tokens), 1);
        const width = Math.max(4, Math.round((day.tokens / max) * 100));
        html += `<div class="usage-bar"><span>${esc(day.date.slice(5))}</span><i style="width:${width}%"></i><em>${fmtNumber(day.tokens)}</em></div>`;
    });
    html += '</div>';
    container.innerHTML = html;
}

async function loadMetrics() {
    switchNav('data');
    const container = $('metricsPanel');
    if (container) container.innerHTML = '<p class="muted">加载中...</p>';
    const data = await guarded('运行指标', () => callApi('get_metrics_dashboard'), { toastError: false });
    const jobs = await guarded('任务列表', () => callApi('list_jobs', 6), { toastError: false });
    if (!container) return;
    if (!data || !data.summary) {
        container.innerHTML = '<p class="muted">暂无运行指标，使用一段时间后再来看。</p>';
        return;
    }
    const s = data.summary;
    let html = `<div class="mini-stats">
        <div><b>${s.startups.last_ms || 0} ms</b><span>最近启动</span></div>
        <div><b>${s.startups.p95_ms || 0} ms</b><span>启动 p95</span></div>
        <div><b>${fmtNumber(s.ai.calls)}</b><span>AI 调用</span></div>
        <div><b>${s.ai.success_rate || 0}%</b><span>成功率</span></div>
        <div><b>${s.ai.p95_latency_ms || 0} ms</b><span>AI p95</span></div>
        <div><b>¥${Number(s.ai.cost || 0).toFixed(4)}</b><span>估算成本</span></div>
        <div><b>${s.crashes || 0}</b><span>崩溃次数</span></div>
        <div><b>${s.crash_rate || 0}%</b><span>崩溃/启动</span></div>
        <div><b>${s.jobs.count || 0}</b><span>后台任务</span></div>
    </div>`;
    html += '<h4>最近启动</h4><div class="list-stack">';
    (data.startups || []).slice(0, 6).forEach((item) => {
        html += `<div class="list-row"><span><b>${item.total_ms} ms</b><small>${esc(item.at || '')} · ${item.frozen ? '打包' : '源码'}</small></span></div>`;
    });
    if (!(data.startups || []).length) html += '<p class="muted">还没有启动记录</p>';
    html += '</div>';
    html += '<h4>AI 任务分布</h4><div class="chip-list">';
    Object.keys(s.ai.tasks || {}).forEach((task) => {
        html += `<span class="chip static">${esc(task)} · ${s.ai.tasks[task]}</span>`;
    });
    html += '</div>';
    html += '<h4>最近任务</h4><div class="list-stack">';
    if (Array.isArray(jobs) && jobs.length) {
        jobs.forEach((job) => {
            const retryable = ['failed', 'interrupted', 'cancelled'].includes(job.status);
            const retryLabel = job.has_checkpoint ? '续跑' : '重试';
            const retry = retryable
                ? `<button class="ghost-btn" onclick="retryJob('${job.id}')">${retryLabel}</button>`
                : '';
            const checkpoint = job.has_checkpoint ? ' · 有断点' : '';
            html += `<div class="list-row"><span><b>${esc(job.kind)}</b><small>${esc(job.status)} · ${job.progress}%${checkpoint} · ${esc(job.message || '')}</small></span>${retry}</div>`;
        });
    } else {
        html += '<p class="muted">还没有后台任务</p>';
    }
    html += '</div>';
    container.innerHTML = html;
}

async function retryJob(id) {
    const ok = await guarded('重试任务', () => callApi('retry_job', id), { toastError: false });
    if (ok) {
        showToast('任务已重新排队', 'info');
        loadMetrics();
    } else {
        showToast('当前状态不能重试', 'error');
    }
}

async function loadReadingHistory() {
    switchNav('data');
    const container = $('readingHistory');
    if (container) container.innerHTML = '<p class="muted">加载中...</p>';
    const rows = await guarded('加载阅读历史', () => callApi('get_reading_history', 20), { toastError: false });
    if (!container) return;
    if (!Array.isArray(rows) || !rows.length) {
        container.innerHTML = '<p class="muted">还没有阅读记录</p>';
        return;
    }
    container.innerHTML = rows.map((item) => `<button class="list-row" onclick="showPanelDetail('${esc(item.classic_id)}')">
        <span><b>${esc(item.title)}</b><small>${esc(item.author)} · ${esc(item.category || '')}</small></span>
        <span class="muted">${esc(String(item.read_at || '').slice(0, 16))}</span>
    </button>`).join('');
}

async function loadProfile() {
    switchNav('data');
    const container = $('profilePanel');
    if (container) container.innerHTML = '<p class="muted">生成中...</p>';
    const data = await guarded('创作画像', () => callApi('get_profile'), { toastError: false });
    if (!container) return;
    if (!data) {
        container.innerHTML = '<p class="muted">还没有作品数据，先去创作几首吧。</p>';
        return;
    }
    let html = `<p>共 ${data.total_works} 篇作品，${fmtNumber(data.total_chars)} 字，平均 ${data.avg_length} 字。</p>`;
    html += '<h4>常用意象</h4><div class="chip-list">';
    (data.imagery_top || []).slice(0, 12).forEach((item) => {
        html += `<span class="chip static">${esc(item[0])} · ${item[1]}</span>`;
    });
    html += '</div><h4>常用主题</h4><div class="chip-list">';
    (data.favorite_topics || []).slice(0, 10).forEach((item) => {
        html += `<span class="chip static">${esc(item[0])} · ${item[1]}</span>`;
    });
    html += '</div>';
    container.innerHTML = html;
}

async function loadBackups() {
    const container = $('backupPanel');
    if (!container) return;
    container.innerHTML = '<p class="muted">加载中...</p>';
    const data = await guarded('加载备份', () => callApi('get_backup_overview'), { toastError: false });
    if (!data) {
        container.innerHTML = '<p class="error-text">加载失败</p>';
        return;
    }
    if ($('backupKeep')) $('backupKeep').value = data.keep_last || 7;
    if (!data.backups || !data.backups.length) {
        container.innerHTML = '<p class="muted">还没有备份，点击「立即备份」创建。</p>';
        return;
    }
    container.innerHTML = data.backups.map((item) => `<div class="backup-row">
        <span><b>${esc(item.filename)}</b><small>${esc(String(item.time || '').replace('T', ' ').slice(0, 19))} · ${Math.round(item.size / 1024)} KB</small></span>
        <span class="backup-actions">
            <button onclick="restoreBackupNamed('${esc(item.filename)}')">恢复</button>
            <button onclick="removeBackup('${esc(item.filename)}')">删除</button>
        </span>
    </div>`).join('');
}

async function saveBackupConfig() {
    const keep = parseInt($('backupKeep') ? $('backupKeep').value : '7', 10) || 7;
    const result = await guarded('保存备份设置', () => callApi('save_backup_config', keep, null));
    if (result) showToast(result.message || '已保存', 'success');
    loadBackups();
}

async function removeBackup(filename) {
    if (!confirm(`删除备份 ${filename}？`)) return;
    const result = await guarded('删除备份', () => callApi('delete_backup', filename));
    if (result) {
        showToast(result.message || '已删除', 'success');
        loadBackups();
    }
}

async function restoreBackupNamed(filename) {
    if (!confirm(`用 ${filename} 覆盖当前数据？系统会先自动备份当前数据。`)) return;
    const result = await guarded('恢复备份', () => callApi('restore_backup', filename), { timeout: 120000 });
    if (!result) return;
    showToast(result.message || (result.success ? '恢复成功' : '恢复失败'), result.success ? 'success' : 'error', 5000);
    if (result.success) {
        loadBackups();
        loadDashboard();
    }
}

async function createBackup() {
    const path = await guarded('创建备份', () => callApi('create_backup'), { timeout: 60000 });
    if (path) {
        const ok = !String(path).includes('失败');
        showToast(ok ? `备份完成：${path}` : path, ok ? 'success' : 'error', 5000);
        loadBackups();
    }
}

async function loadPlugins() {
    const container = $('pluginList');
    if (container) container.innerHTML = '<p class="muted">加载中...</p>';
    const rows = await guarded('加载插件', () => callApi('list_plugins'), { toastError: false });
    if (!container) return;
    if (!Array.isArray(rows) || !rows.length) {
        container.innerHTML = '<p class="muted">未安装插件。将插件放入 plugins/ 目录后重启即可。</p>';
        return;
    }
    container.innerHTML = rows.map((item) => `<div class="list-row"><span><b>${esc(item.name)}</b><small>${esc(item.description || item.genre_name || '')}</small></span></div>`).join('');
}

async function runValidate() {
    const result = await guarded('数据库健康检查', () => callApi('validate_database'), { timeout: 60000 });
    if (!result) return;
    let html = '<b>数据库健康报告</b><br>';
    html += `总篇数：${result.stats.total}　总字数：${fmtNumber(result.stats.total_chars)}<br>`;
    html += `质量均分：${result.quality.avg_score}<br>`;
    html += `缺失分类：${esc((result.missing || []).join('、') || '无')}<br>`;
    html += `AI 评分：${esc((result.report && result.report.health_score) || '暂无')}<br>`;
    html += `建议：${esc(((result.report && result.report.suggestions) || []).join('；') || '暂无')}`;
    if ($('validateResult')) $('validateResult').innerHTML = html;
}

async function runCleanAndOrganize() {
    if (!confirm('确定执行数据清洗？将删除低质量与重复条目，执行前会自动备份。')) return;
    showToast('清洗中，请稍候...', 'info', 6000);
    const result = await guarded('数据清洗', () => callApi('clean_and_organize_database', 30, true, true), { timeout: 180000 });
    if (!result) return;
    alert(`清洗完成！\n删除条目：${result.removed} 条\n重复条目：${result.duplicates} 条\n整理更新：${result.updated} 条\n剩余总数：${result.remaining} 条`);
    loadDashboard();
}

async function showQualityReport() {
    switchNav('data');
    const result = await guarded('质量报告', () => callApi('quality_report'), { timeout: 120000 });
    if (!result) return;
    let html = '<h3>质量报告</h3>';
    html += `<p><b>总体均分：</b>${result.overall.avg_score}</p><p><b>等级分布：</b></p><ul>`;
    Object.keys(result.overall.grades || {}).forEach((grade) => {
        html += `<li>${esc(grade)} 级：${result.overall.grades[grade]} 篇</li>`;
    });
    html += '</ul>';
    if ($('validateResult')) $('validateResult').innerHTML = html;
}

async function startExpand() {
    const category = $('expandCat') ? $('expandCat').value : '唐诗';
    const era = $('expandEra') ? $('expandEra').value : '';
    const school = $('expandSchool') ? $('expandSchool').value : '';
    const count = parseInt(($('expandCount') || {}).value, 10) || 10;
    const progress = $('expandProgress');
    if (progress) progress.innerHTML = '<div class="progress-bar-fill" style="width:2%"></div>';
    showToast('扩充已开始，可随时取消', 'info', 5000);
    let result = null;
    try {
        result = await runJob(
            'expand',
            { era, genre: '', school, category, count },
            {
                timeout: 240000,
                onProgress: (job) => {
                    if (progress) {
                        progress.innerHTML = `<div class="progress-bar-fill" style="width:${Math.max(2, job.progress)}%"></div>`;
                    }
                    if ($('expandPreview')) {
                        $('expandPreview').textContent = `${Math.round(job.progress)}% ${job.message || ''}`;
                    }
                },
            }
        );
    } catch (error) {
        showToast(`扩充失败：${error.message || error}`, 'error', 5000);
        return;
    } finally {
        if (progress) progress.innerHTML = '';
    }
    if (result) {
        if ($('expandPreview')) $('expandPreview').textContent = `已导入 ${result.imported || 0} 篇（候选 ${result.total || 0} 篇）`;
        showToast(`扩充完成，导入 ${result.imported || 0} 篇`, 'success', 5000);
        loadDashboard();
    }
}

async function previewExpand() {
    const category = $('previewCat') ? $('previewCat').value : '唐诗';
    const count = parseInt(($('previewCount') || {}).value, 10) || 5;
    const container = $('previewList');
    if (!container) return;
    container.innerHTML = '<p class="muted">正在生成候选，请稍候...</p>';
    const rows = await guarded('生成候选项', () => callApi('get_expand_candidates', '', '', '', category, count), { timeout: 60000 });
    state.preview = Array.isArray(rows) ? rows : [];
    state.previewSelected = new Set(state.preview.map((_, index) => index));
    renderPreview();
}

function renderPreview() {
    const container = $('previewList');
    if (!container) return;
    if (!state.preview.length) {
        container.innerHTML = '<p class="muted">暂无候选，请重试或检查 API 设置</p>';
        if ($('previewActions')) $('previewActions').style.display = 'none';
        return;
    }
    container.innerHTML = state.preview.map((item, index) => {
        const selected = state.previewSelected.has(index) ? 'selected' : '';
        return `<div class="preview-item ${selected}" data-index="${index}">
            <span class="preview-title">${esc(item.title)}</span>
            <span class="preview-meta">${esc(item.author)} ${esc(item.dynasty || '')}</span>
        </div>`;
    }).join('');
    container.querySelectorAll('.preview-item').forEach((element) => {
        element.onclick = () => {
            const index = Number(element.dataset.index);
            if (state.previewSelected.has(index)) state.previewSelected.delete(index);
            else state.previewSelected.add(index);
            renderPreview();
        };
    });
    if ($('previewActions')) $('previewActions').style.display = 'block';
}

function togglePreviewSelect(index) {
    if (state.previewSelected.has(index)) state.previewSelected.delete(index);
    else state.previewSelected.add(index);
    renderPreview();
}

async function confirmImport() {
    const chosen = Array.from(state.previewSelected).map((index) => state.preview[index]).filter(Boolean);
    if (!chosen.length) return showToast('请至少选择一条', 'error');
    if (!confirm(`将导入 ${chosen.length} 条，每条需调用 AI 获取全文，可能耗时较长。继续？`)) return;
    showToast('导入已开始，可随时取消', 'info', 6000);
    let result = null;
    try {
        result = await runJob(
            'import',
            { candidates: chosen },
            {
                timeout: 300000,
                onProgress: (job) => {
                    if ($('previewList')) {
                        $('previewList').textContent = `导入中 ${Math.round(job.progress)}% ${job.message || ''}`;
                    }
                },
            }
        );
    } catch (error) {
        showToast(`导入失败：${error.message || error}`, 'error', 5000);
        return;
    }
    if (result) {
        alert(`导入完成：${result.imported} 条`);
        cancelPreview();
        loadTeachCats();
        loadDashboard();
    }
}

function cancelPreview() {
    state.preview = [];
    state.previewSelected.clear();
    if ($('previewList')) $('previewList').innerHTML = '';
    if ($('previewActions')) $('previewActions').style.display = 'none';
}

/* ---------------- 朗读 ---------------- */
function openSpeakPanel() {
    if (!state.speakContent) return showToast('没有可朗读的内容', 'error');
    state.speakLines = state.speakContent.split('\n').filter((line) => line.trim());
    state.speakIndex = 0;
    if ($('speakPanel')) $('speakPanel').classList.remove('hidden');
    if ($('speakOverlay')) $('speakOverlay').classList.remove('hidden');
    if ($('speakStatus')) $('speakStatus').textContent = '准备朗读...';
}

function closeSpeakPanel() {
    stopSpeak();
    if ($('speakPanel')) $('speakPanel').classList.add('hidden');
    if ($('speakOverlay')) $('speakOverlay').classList.add('hidden');
}

function speechAvailable() {
    if (!('speechSynthesis' in window)) {
        showToast('当前系统不支持语音合成', 'error');
        return false;
    }
    return true;
}

async function ttsParams(text) {
    const voice = $('spVoice') ? $('spVoice').value : ($('ttsVoice') ? $('ttsVoice').value : 'female');
    const style = $('ttsStyle') ? $('ttsStyle').value : 'normal';
    const speed = parseFloat($('ttsSpeed') ? $('ttsSpeed').value : '1') || 1;
    const params = await guarded('计算朗读参数', () => callApi('speak_text', text, voice, style, speed), { toastError: false });
    return params || { rate: speed, pitch: 1 };
}

async function startFullSpeak() {
    if (!speechAvailable() || !state.speakContent) return;
    stopSpeak();
    const params = await ttsParams(state.speakContent);
    const utterance = new SpeechSynthesisUtterance(state.speakContent);
    utterance.lang = 'zh-CN';
    utterance.rate = params.rate || 1;
    utterance.pitch = params.pitch || 1;
    utterance.onend = () => { if ($('speakStatus')) $('speakStatus').textContent = '朗读完成'; };
    state.speakUtterance = utterance;
    window.speechSynthesis.speak(utterance);
    if ($('speakStatus')) $('speakStatus').textContent = '全文朗读中...';
}

function startLineSpeak() {
    if (!speechAvailable()) return;
    stopSpeak();
    state.speakIndex = 0;
    speakNextLine();
}

async function speakNextLine() {
    if (state.speakIndex >= state.speakLines.length) {
        if ($('speakStatus')) $('speakStatus').textContent = '朗读完成';
        return;
    }
    const params = await ttsParams(state.speakLines[state.speakIndex]);
    const utterance = new SpeechSynthesisUtterance(state.speakLines[state.speakIndex]);
    utterance.lang = 'zh-CN';
    utterance.rate = params.rate || 1;
    utterance.pitch = params.pitch || 1;
    utterance.onend = () => {
        state.speakIndex += 1;
        speakNextLine();
    };
    state.speakUtterance = utterance;
    window.speechSynthesis.speak(utterance);
    if ($('speakStatus')) $('speakStatus').textContent = `第 ${state.speakIndex + 1} / ${state.speakLines.length} 句`;
}

function pauseSpeak() { if (window.speechSynthesis) window.speechSynthesis.pause(); }
function resumeSpeak() { if (window.speechSynthesis) window.speechSynthesis.resume(); }
function stopSpeak() {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    state.speakUtterance = null;
}

function loadTtsOptions() {
    const speed = parseFloat(($('ttsSpeed') || {}).value || '1');
    if ($('ttsSpeedVal')) $('ttsSpeedVal').textContent = `${speed.toFixed(1)}x`;
}

async function testSpeak() {
    if (!speechAvailable()) return;
    const text = '心语朗读测试：明月松间照，清泉石上流。';
    const params = await ttsParams(text);
    stopSpeak();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'zh-CN';
    utterance.rate = params.rate || 1;
    utterance.pitch = params.pitch || 1;
    window.speechSynthesis.speak(utterance);
    showToast('正在试听朗读', 'info');
}

/* ---------------- 设置 ---------------- */
async function openSettings() {
    const settings = await guarded('读取设置', () => callApi('get_settings'));
    if (!settings) return;
    state.apiProviders = settings.providers || [];
    const panel = $('classicsPanel');
    const overlay = $('classicsOverlay');
    if (panel) panel.classList.remove('hidden');
    if (overlay) overlay.classList.remove('hidden');
    const header = $('classicsHeader');
    if (header) header.querySelector('span').textContent = 'API 设置';

    let html = '<h3>API 设置</h3>';
    html += '<label>服务商</label><select id="apiProvider">';
    state.apiProviders.forEach((provider) => {
        html += `<option value="${esc(provider.id)}" ${settings.provider === provider.id ? 'selected' : ''}>${esc(provider.name)}</option>`;
    });
    html += '</select><p id="providerDesc" class="muted"></p>';
    html += `<label>API Key</label>
        <div class="key-row"><input type="password" id="apiKeyInput" value="${settings.has_key ? 'KEPT' : ''}">
        <button id="toggleKey" class="btn-icon">显示</button></div>
        <p class="muted">已保存的 Key 显示为 KEPT，不修改即保持原值。</p>`;
    html += '<label>模型</label><select id="apiModel"></select>';
    html += `<label>温度：<span id="tempDisplay">${esc(settings.temperature)}</span></label>
        <input type="range" id="apiTemp" min="0" max="2" step="0.1" value="${esc(settings.temperature)}">`;
    html += `<label>最大长度：<span id="maxTokensDisplay">${esc(settings.max_tokens)}</span></label>
        <input type="range" id="apiMaxTokens" min="64" max="4096" step="64" value="${esc(settings.max_tokens)}">`;
    html += `<label>超时（秒）</label><input type="number" id="apiTimeout" min="5" max="120" value="${esc(settings.timeout)}">`;
    html += `<label>重试次数</label><select id="apiRetry">${[0, 1, 2, 3].map((value) =>
        `<option value="${value}" ${settings.retry === value ? 'selected' : ''}>${value} 次</option>`).join('')}</select>`;
    html += `<label class="check-line"><input type="checkbox" id="apiIsDefault" ${settings.is_default ? 'checked' : ''}>设为默认配置</label>`;
    const usage = settings.usage || {};
    html += `<div class="mini-stats"><div><b>${fmtNumber(usage.monthly_calls)}</b><span>本月调用</span></div>
        <div><b>${fmtNumber(usage.monthly_tokens)}</b><span>本月 Token</span></div></div>`;
    html += '<div class="action-row"><button class="primary-btn" id="saveApiBtn">保存设置</button><button id="testApiBtn">测试连接</button></div>';
    html += '<p id="apiTestResult" class="muted"></p>';

    const content = $('classicsContent');
    if (!content) return;
    content.innerHTML = html;
    if ($('classicsPagination')) $('classicsPagination').innerHTML = '';
    if ($('apiProvider')) $('apiProvider').onchange = () => onProviderChange();
    if ($('apiTemp')) $('apiTemp').oninput = () => { $('tempDisplay').textContent = $('apiTemp').value; };
    if ($('apiMaxTokens')) $('apiMaxTokens').oninput = () => { $('maxTokensDisplay').textContent = $('apiMaxTokens').value; };
    if ($('toggleKey')) $('toggleKey').onclick = () => {
        const input = $('apiKeyInput');
        input.type = input.type === 'password' ? 'text' : 'password';
    };
    if ($('saveApiBtn')) $('saveApiBtn').onclick = saveApiSettings;
    if ($('testApiBtn')) $('testApiBtn').onclick = testApiKey;
    onProviderChange(settings.model);
}

function onProviderChange(preferredModel) {
    const providerId = $('apiProvider') ? $('apiProvider').value : '';
    const provider = state.apiProviders.find((item) => item.id === providerId);
    const select = $('apiModel');
    if (!provider || !select) return;
    select.innerHTML = '';
    (provider.models || []).forEach((model) => {
        const option = document.createElement('option');
        option.value = model;
        option.textContent = model;
        if (preferredModel && model === preferredModel) option.selected = true;
        select.appendChild(option);
    });
    if ($('providerDesc')) $('providerDesc').textContent = provider.desc || '';
}

async function saveApiSettings() {
    const provider = $('apiProvider').value;
    const key = $('apiKeyInput').value.trim();
    const model = $('apiModel').value;
    const temperature = parseFloat($('apiTemp').value);
    const maxTokens = parseInt($('apiMaxTokens').value, 10);
    const timeout = parseInt($('apiTimeout').value, 10) || 30;
    const retry = parseInt($('apiRetry').value, 10);
    const isDefault = $('apiIsDefault').checked;
    const message = await guarded('保存设置', () =>
        callApi('save_api_settings', provider, key, model, temperature, maxTokens, timeout, retry, isDefault)
    );
    if (!message) return;
    if (String(message).includes('失败')) return showToast(message, 'error', 5000);
    showToast(message, 'success');
    if ($('apiKeyInput')) $('apiKeyInput').value = 'KEPT';
    updateApiStatus();
    loadDashboard();
}

async function testApiKey() {
    const key = $('apiKeyInput').value.trim();
    if (!key || key === 'KEPT') return showToast('请输入新的 API Key 再测试', 'error');
    const provider = $('apiProvider').value;
    if ($('apiTestResult')) $('apiTestResult').textContent = '正在测试...';
    const result = await guarded('测试连接', () => callApi('test_api_key', key, provider), { toastError: false });
    if (!result) return;
    if ($('apiTestResult')) {
        $('apiTestResult').textContent = (result.success ? '✅ ' : '❌ ') + (result.message || '');
        $('apiTestResult').style.color = result.success ? '#2e7d32' : '#c0392b';
    }
}

async function updateApiStatus() {
    const box = $('apiStatus');
    if (!box) return;
    box.textContent = '检查中...';
    const result = await guarded('检查 API 状态', () => callApi('check_api_status'), { toastError: false });
    if (!result) {
        box.textContent = '未连接';
        return;
    }
    box.innerHTML = result.success
        ? `<span class="ok">✅ ${esc(result.message || '连接正常')}</span>`
        : `<span class="bad">❌ ${esc(result.message || '连接失败')}</span>`;
}

async function testCurrentApi() {
    const box = $('apiStatus');
    if (box) box.textContent = '测试中...';
    const result = await guarded('测试当前 API', () => callApi('check_api_status'));
    if (!result || !box) return;
    box.innerHTML = result.success
        ? `<span class="ok">✅ ${esc(result.message || '连接正常')}</span>`
        : `<span class="bad">❌ ${esc(result.message || '连接失败')}</span>`;
}

async function loadSettingsExtras() {
    const url = await guarded('读取更新源', () => callApi('get_update_url'), { toastError: false });
    if ($('updateUrl') && url !== null) $('updateUrl').value = url || '';
    const themeSelect = $('themeSelect');
    if (themeSelect) themeSelect.value = state.theme;
}

async function saveUpdateUrl() {
    const url = $('updateUrl') ? $('updateUrl').value.trim() : '';
    const result = await guarded('保存更新源', () => callApi('save_update_url', url));
    if (result) showToast(result, 'success');
}

async function clearCache() {
    const result = await guarded('清理缓存', () => callApi('clear_cache'));
    if (result) showToast(result, 'success');
}

function openDocumentPanel(title) {
    const panel = $('classicsPanel');
    const overlay = $('classicsOverlay');
    if (panel) panel.classList.remove('hidden');
    if (overlay) overlay.classList.remove('hidden');
    const header = $('classicsHeader');
    if (header) header.querySelector('span').textContent = title;
    if ($('classicsPagination')) $('classicsPagination').innerHTML = '';
}

async function showLegal(name) {
    const text = await guarded('读取文档', () => callApi('get_legal_document', name));
    if (!text) return;
    openDocumentPanel(name === 'terms' ? '用户协议' : '隐私政策');
    if ($('classicsContent')) {
        $('classicsContent').innerHTML = `<pre class="legal-text">${esc(text)}</pre>`;
    }
}

async function exportDiagnostics() {
    const path = await guarded('导出诊断', () => callApi('export_diagnostics'), { timeout: 30000 });
    if (path) showToast(`诊断包已导出：${path}`, 'success', 6000);
}

async function exportUserData() {
    const path = await guarded('导出我的数据', () => callApi('export_user_data'), { timeout: 30000 });
    if (path) showToast(`数据已导出：${path}`, 'success', 6000);
}

async function resetUserData() {
    const answer = prompt('这会清空作品、笔记、收藏、阅读历史和聊天记录（经典库与设置保留）。\n输入 DELETE 确认，系统会先自动备份：', '');
    if (!answer) return;
    if (answer.trim().toUpperCase() !== 'DELETE') return showToast('输入不匹配，已取消', 'error');
    const result = await guarded('清空数据', () => callApi('reset_user_data', answer), { timeout: 60000 });
    if (!result) return;
    if (!result.success) return showToast(result.message || '清空失败', 'error', 5000);
    showToast(`${result.message}；安全备份：${result.backup || '无'}`, 'success', 8000);
    loadDashboard();
    loadBackups();
}

async function checkUpdate() {
    const result = await guarded('检查更新', () => callApi('check_update'));
    if (!result) return;
    if (!result.has_update) {
        alert(`当前版本 V${result.current}\n${result.message || '已是最新版本'}`);
        return;
    }
    const summary = `发现新版本 V${result.latest}\n${result.message || ''}\n${result.signature_verified ? '签名已校验' : '未签名/开发源'} · 灰度 ${result.rollout}%`;
    if (!confirm(`${summary}\n\n是否下载更新包？`)) return;
    const download = await guarded('下载更新', () => callApi('download_update', result.url, result.sha256), { timeout: 180000 });
    if (!download || !download.success) {
        return showToast((download && download.message) || '下载失败', 'error', 6000);
    }
    if (!confirm(`更新包已下载并通过校验：\n${download.path}\n\n现在启动安装程序？应用将退出。`)) {
        return showToast(`更新包位置：${download.path}`, 'info', 8000);
    }
    const installed = await guarded('启动安装', () => callApi('install_update', download.path));
    if (installed && installed.success) {
        showToast(installed.message || '已启动安装程序', 'success', 5000);
    } else {
        showToast((installed && installed.message) || '安装启动失败', 'error', 6000);
    }
}

async function showAbout() {
    const info = await guarded('读取版本', () => callApi('get_version_info'));
    if (!info) return;
    alert(`${info.name} V${info.version}\n${info.codename}\n作者：${info.author}\n\n功能：${(info.features || []).join('、')}`);
}

function showShortcuts() {
    alert('快捷键\nCtrl+K：命令面板\nCtrl+Enter：生成作品\nCtrl+S：保存作品\nEsc：关闭面板');
}

/* ---------------- 命令面板 ---------------- */
function commandList() {
    return [
        { label: '新建创作', hint: '打开创作工坊', action: () => switchNav('creation') },
        { label: '随机主题创作', hint: '生成一个主题并开始', action: () => { switchNav('creation'); randomTopic(); } },
        { label: '随机经典', hint: '随机打开一篇经典赏析', action: getRandomClassic },
        { label: '搜索经典', hint: '聚焦文库搜索框', action: () => { switchNav('classics'); $('classicSearch').focus(); } },
        { label: '每日一诗', hint: '查看今天的推荐', action: openDaily },
        { label: '用量统计', hint: '查看 Token 与费用', action: loadUsageDashboard },
        { label: '阅读历史', hint: '最近读过的作品', action: loadReadingHistory },
        { label: '创作画像', hint: '统计你的意象与主题', action: loadProfile },
        { label: '立即备份', hint: '创建本地备份', action: createBackup },
        { label: '备份中心', hint: '查看与恢复备份', action: () => { switchNav('data'); loadBackups(); } },
        { label: '数据库健康', hint: '检查数据质量', action: () => { switchNav('data'); runValidate(); } },
        { label: '质量报告', hint: '查看等级分布', action: showQualityReport },
        { label: 'API 设置', hint: '配置模型与 Key', action: openSettings },
        { label: '切换主题', hint: '宣纸 / 水墨 / 夜间', action: cycleTheme },
        { label: '清理缓存', hint: '清空检索与创作缓存', action: clearCache },
        { label: '检查更新', hint: '获取新版本', action: checkUpdate },
    ];
}

function openCmdk() {
    const overlay = $('cmdkOverlay');
    if (!overlay) return;
    overlay.classList.remove('hidden');
    if ($('cmdkInput')) {
        $('cmdkInput').value = '';
        $('cmdkInput').focus();
    }
    filterCmdk();
}

function closeCmdk() {
    if ($('cmdkOverlay')) $('cmdkOverlay').classList.add('hidden');
}

function filterCmdk() {
    const keyword = ($('cmdkInput') ? $('cmdkInput').value : '').trim().toLowerCase();
    state.cmdkItems = commandList().filter((item) =>
        !keyword || item.label.toLowerCase().includes(keyword) || item.hint.toLowerCase().includes(keyword)
    );
    state.cmdkIndex = 0;
    renderCmdk();
}

function renderCmdk() {
    const list = $('cmdkList');
    if (!list) return;
    list.innerHTML = state.cmdkItems.map((item, index) =>
        `<button class="cmdk-item ${index === state.cmdkIndex ? 'active' : ''}" data-index="${index}">
            <b>${esc(item.label)}</b><span>${esc(item.hint)}</span>
        </button>`
    ).join('') || '<p class="muted">没有匹配的命令</p>';
    list.querySelectorAll('.cmdk-item').forEach((button) => {
        button.onclick = () => runCmdk(Number(button.dataset.index));
    });
}

function handleCmdkKey(event) {
    if (event.key === 'ArrowDown') {
        event.preventDefault();
        state.cmdkIndex = Math.min(state.cmdkItems.length - 1, state.cmdkIndex + 1);
        renderCmdk();
    } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        state.cmdkIndex = Math.max(0, state.cmdkIndex - 1);
        renderCmdk();
    } else if (event.key === 'Enter') {
        event.preventDefault();
        runCmdk(state.cmdkIndex);
    }
}

function runCmdk(index) {
    const item = state.cmdkItems[index];
    if (!item) return;
    closeCmdk();
    try {
        const result = item.action();
        if (result && typeof result.catch === 'function') result.catch(() => {});
    } catch (error) {
        showToast(`命令执行失败：${error.message || error}`, 'error');
    }
}

/* ---------------- 聊天 ---------------- */
function addChatMsg(role, text) {
    const container = $('chatMessages');
    if (!container) return;
    const wrapper = document.createElement('div');
    wrapper.className = `chat-msg ${role === 'user' ? 'user' : 'ai'}`;
    wrapper.innerHTML = `<div class="bubble">${esc(text).replace(/\n/g, '<br>')}</div>`;
    container.appendChild(wrapper);
    wrapper.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function sendChat() {
    const input = $('chatInput');
    if (!input) return;
    const message = input.value.trim();
    if (!message) return;
    input.value = '';
    addChatMsg('user', message);
    state.chatHistory.push({ role: 'user', content: message });
    processCommand(message);
}

async function processCommand(message) {
    const parts = message.split(/\s+/);
    const command = parts[0].toLowerCase();
    try {
        if (command === '/deep') {
            const keyword = parts.slice(1).join(' ');
            const rows = await callApi('search_classics_v2', keyword, '', '', '', 1);
            if (!rows || !rows.length) return addChatMsg('ai', '未找到相关作品。');
            const analysis = await withTimeout(callApi('deep_analysis', rows[0].id), 20000, '赏析');
            if (!analysis || analysis.error) return addChatMsg('ai', '赏析暂不可用，请检查 API 设置。');
            addChatMsg('ai', `《${rows[0].title}》\n背景：${analysis.background || '暂无'}\n解读：${analysis.text_analysis || '暂无'}\n意境：${analysis.artistic || '暂无'}\n格律：${analysis.rhythm || '暂无'}\n文化：${analysis.culture || '暂无'}\n教学：${analysis.teaching || '暂无'}`);
            return;
        }
        if (command === '/write') {
            const genre = parts[1] || '五言绝句';
            const style = parts[2] || '';
            const topic = parts.slice(3).join(' ') || '秋夜';
            const styleInfo = style ? { instruction: `模仿${style}风格` } : null;
            const results = await callApi('generate', genre, topic, styleInfo);
            addChatMsg('ai', `✍️ ${Array.isArray(results) ? results[0] : results}`);
            return;
        }
        if (command === '/expand') {
            const category = parts[1] || '唐诗';
            const count = parseInt(parts[2], 10) || 10;
            addChatMsg('ai', '正在扩充，请稍候...');
            const result = await withTimeout(callApi('smart_expand_advanced', '', '', '', category, count), 120000, '扩充');
            addChatMsg('ai', `已扩充 ${result && result.imported ? result.imported : 0} 篇。`);
            return;
        }
        if (command === '/stats') {
            const stats = await callApi('get_classic_stats');
            addChatMsg('ai', `总篇数：${stats.total}\n总字数：${fmtNumber(stats.total_chars)}\n质量均分：${stats.quality_avg}\n最近扩充：${stats.recent_expand} 次`);
            return;
        }
        if (command === '/help') {
            const help = await callApi('get_help_info');
            addChatMsg('ai', `命令：\n${(help.commands || []).join('\n')}\n\n技巧：\n${(help.tips || []).join('\n')}`);
            return;
        }
        if (command === '/clear') {
            clearChat();
            return;
        }
        const answer = await withTimeout(callApi('chat', message, JSON.stringify(state.chatHistory.slice(-20))), 30000, 'AI 回复');
        addChatMsg('ai', answer || '（无回复）');
        state.chatHistory.push({ role: 'assistant', content: String(answer || '') });
        if (state.chatHistory.length > 40) state.chatHistory = state.chatHistory.slice(-40);
    } catch (error) {
        addChatMsg('ai', `请求失败：${error.message || error}。请检查网络或 API 设置。`);
        const warning = $('apiWarning');
        if (warning) warning.classList.remove('hidden');
    }
}

function clearChat() {
    if (state.typingTimer) clearInterval(state.typingTimer);
    state.chatHistory = [];
    const container = $('chatMessages');
    if (container) container.innerHTML = '<div class="chat-msg ai"><div class="bubble">对话已清空</div></div>';
    callApi('save_chat_history', '[]').catch(() => {});
    showStatus('对话已清空');
}

async function loadChatHistory() {
    try {
        const raw = await callApi('load_chat_history');
        const rows = JSON.parse(raw || '[]');
        if (!Array.isArray(rows) || !rows.length) return;
        state.chatHistory = rows.slice(-20);
        rows.slice(-10).forEach((item) => {
            addChatMsg(item.role === 'user' ? 'user' : 'ai', item.content || '');
        });
    } catch (error) {
        /* 历史记录损坏时忽略 */
    }
}

/* ---------------- 杂项 ---------------- */
async function randomTopic() {
    const topic = await guarded('随机主题', () => callApi('get_random_topic'), { toastError: false });
    if (topic && $('creationTopic')) {
        $('creationTopic').value = topic;
        showStatus(`主题：${topic}`);
    }
}

/* 兼容旧入口 */
function saveWork() { return saveCreation(); }
