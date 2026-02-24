/* ============================================================
   app.js — Anime Goods Tracker PWA v4 (Starbucks Style)
   ============================================================ */

const API_BASE = (location.hostname === "localhost" || location.hostname === "127.0.0.1")
    ? "http://localhost:5000"
    : "";
let allItems = [];
let currentItems = []; // 表示対象となる現在のコレクション（フィルタ・検索後）
let currentCategory = "all";
let isSearchMode = false;
const DISPLAY_STEP = 9;   // 1回に表示する件数
let displayLimit = DISPLAY_STEP; // 現在の表示上限

// Auth State
let authToken = localStorage.getItem("token") || null;
let currentUser = localStorage.getItem("email") || null;
let currentDisplayName = localStorage.getItem("displayName") || null;
let myFavorites = [];

// ── DOM Elements ──
const cardsContainer = document.getElementById("cards-container");
const trendingContainer = document.getElementById("trending-container");
const loadingEl = document.getElementById("loading");
const emptyEl = document.getElementById("empty-state");
const searchInput = document.getElementById("hero-search-input");
const searchBtn = document.getElementById("hero-search-btn");
const sectionHeading = document.getElementById("section-heading");
const toastEl = document.getElementById("toast");
const filterBtns = document.querySelectorAll(".filter-btn");

// Hero Section DOM
const heroSection = document.getElementById("hero-section");
const heroBg = document.getElementById("hero-bg");
const heroCategory = document.getElementById("hero-category");
const heroTitle = document.getElementById("hero-title");
const heroDesc = document.getElementById("hero-desc");
const heroLink = document.getElementById("hero-link");

// Auth DOM
const authModal = document.getElementById("auth-modal");
const modalClose = document.getElementById("modal-close");
const authForm = document.getElementById("auth-form");
const authEmail = document.getElementById("auth-email");
const authPw = document.getElementById("auth-pw");
const authToggle = document.getElementById("auth-toggle");
const authTitle = document.getElementById("auth-title");
const authSubmit = document.getElementById("auth-submit");
const btnLoginOpen = document.getElementById("btn-login-open");
const userProfile = document.getElementById("user-profile");
const userDisplayName = document.getElementById("user-display-name");
const btnLogout = document.getElementById("btn-logout");
let isLoginMode = true;

function updateHeaderAuth() {
    if (authToken && currentUser) {
        if (btnLoginOpen) btnLoginOpen.classList.add("hidden");
        if (userProfile) userProfile.classList.remove("hidden");
        // displayNameがあればそちらを優先、なければメールの@前を使う
        const displayLabel = currentDisplayName || currentUser.split("@")[0];
        if (userDisplayName) userDisplayName.textContent = displayLabel;
    } else {
        if (btnLoginOpen) btnLoginOpen.classList.remove("hidden");
        if (userProfile) userProfile.classList.add("hidden");
    }
}

function setLoading(isLoading) {
    if (isLoading) {
        loadingEl.classList.remove("hidden");
        cardsContainer.classList.add("hidden");
        emptyEl.classList.add("hidden");
    } else {
        loadingEl.classList.add("hidden");
        cardsContainer.classList.remove("hidden");
    }
}

function showToast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add("show");
    setTimeout(() => toastEl.classList.remove("show"), 3000);
}

// ── Item Filtering ──
function applyFilters(items) {
    let filtered = items;
    if (currentCategory === "favorites") {
        // お気に入り一覧タブが選ばれた場合
        filtered = filtered.filter(i => myFavorites.includes(i.title));
    } else if (currentCategory !== "all") {
        filtered = filtered.filter(i => i.category === currentCategory);
    }
    return filtered;
}

// ── タイトルからアニメ名を抽出し、重複を排除する ──
function getUniqueAnimeItems(items) {
    const uniqueItems = [];
    const usedKeywords = new Set();

    function extractKeywords(title) {
        const match = title.match(/[『【「](.+?)[』】」]/);
        if (match) return match[1];
        return title.substring(0, Math.min(title.length, 6));
    }

    for (const item of items) {
        const kw = extractKeywords(item.title);
        if (!usedKeywords.has(kw)) {
            usedKeywords.add(kw);
            uniqueItems.push(item);
        }
    }
    return uniqueItems;
}

// ── API Fetch ──
async function fetchFavorites() {
    if (!authToken) return;
    try {
        const res = await fetch(`${API_BASE}/api/favorites`, {
            headers: { "Authorization": `Bearer ${authToken}` }
        });
        const json = await res.json();
        if (json.status === "ok") myFavorites = json.favorites || [];
    } catch (e) {
        console.error("fetchFavorites error", e);
    }
}

async function fetchData() {
    try {
        if (authToken) await fetchFavorites();
        const res = await fetch(`${API_BASE}/api/items?sort=score`);
        const json = await res.json();
        allItems = json.items || [];

        currentItems = applyFilters(allItems);

        // トップページ（検索していない＆全て表示の場合）は、いろいろなアニメが出るように重複排除
        let displayItems = currentItems;
        if (!isSearchMode && currentCategory === "all") {
            displayItems = getUniqueAnimeItems(currentItems);
        }

        if (!isSearchMode) {
            sectionHeading.textContent = "Latest Journal";
            if (displayItems.length > 0) renderHero(displayItems.slice(0, 5)); // 後でスライダー用に複数渡す準備
            else renderHero([]);
            renderItems(displayItems.slice(0, displayLimit));
            updateShowMoreBtn(displayItems);
            renderTrendingSeeds(allItems); // トレンド表示
        } else {
            if (displayItems.length > 0) renderHero(displayItems.slice(0, 5));
            else renderHero([]);
            renderItems(displayItems.slice(0, displayLimit));
            updateShowMoreBtn(displayItems);
            renderTrendingSeeds(allItems);
        }
    } catch (e) {
        console.error("fetchData error", e);
        showToast("⚠️ データ取得に失敗しました");
    }
}

// ── 検索＆自動追加起動 ──
async function onSearch(query) {
    isSearchMode = true;
    displayLimit = DISPLAY_STEP;
    sectionHeading.textContent = `Results for "${query}"`;
    setLoading(true);

    try {
        const res = await fetch(`${API_BASE}/api/search`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: query })
        });
        const json = await res.json();

        if (json.status === "ok") {
            showToast(`✨ 「${query}」を追加！クローラが情報を探し始めました`);

            setTimeout(async () => {
                const res2 = await fetch(`${API_BASE}/api/items?sort=score`);
                const json2 = await res2.json();
                allItems = json2.items || [];

                let searched = allItems.filter(i => i.title.includes(query) || i.content.includes(query));
                currentItems = applyFilters(searched);

                setLoading(false);
                if (currentItems.length > 0) renderHero(currentItems.slice(0, 5));
                else renderHero([]);
                renderItems(currentItems.slice(0, displayLimit));
                updateShowMoreBtn(currentItems);
            }, 3000);

        } else {
            setLoading(false);
            showToast(`⚠️ エラー: ${json.message}`);
        }
    } catch (e) {
        console.error(e);
        setLoading(false);
        showToast("⚠️ サーバー通信エラー");
    }
}

// ── もっと見るボタン管理 ──
function updateShowMoreBtn(allFiltered) {
    let btn = document.getElementById('show-more-btn');
    if (displayLimit >= allFiltered.length) {
        if (btn) btn.remove();
        return;
    }
    if (!btn) {
        btn = document.createElement('div');
        btn.id = 'show-more-btn';
        btn.className = 'show-more-wrapper';
        btn.innerHTML = `<button class="show-more-btn">もっと見る <span class="show-more-count"></span></button>`;
        cardsContainer.parentNode.insertBefore(btn, cardsContainer.nextSibling);
        btn.querySelector('button').addEventListener('click', () => {
            displayLimit += DISPLAY_STEP;
            renderItems(currentItems.slice(0, displayLimit));
            updateShowMoreBtn(currentItems);
        });
    }
    const remaining = allFiltered.length - displayLimit;
    btn.querySelector('.show-more-count').textContent = `（残り ${remaining} 件）`;
}

// ── シェア機能 ──
async function shareItem(title, url) {
    const text = `🌿 Animation Roastery
${title}
${url}`;
    if (navigator.share) {
        try {
            await navigator.share({ title: title, text: text, url: url });
        } catch (e) { /* キャンセルは無視 */ }
    } else {
        // フォールバック: クリップボードにコピー
        try {
            await navigator.clipboard.writeText(text);
            showToast('🔗 URLをクリップボードにコピーしました');
        } catch (e) {
            showToast('⚠️ コピーに失敗しました');
        }
    }
}

// ── レンダリング（ヒーローセクション表示スライダー） ──
let heroIntervalId = null;
function renderHero(items) {
    if (!heroSection || !items || items.length === 0) {
        if (heroSection) heroSection.classList.add("hidden");
        return;
    }

    heroSection.classList.remove("hidden");
    let currentIndex = 0;

    // 現在表示中のHeroアイテムをDOMに反映する関数
    const updateHeroDOM = (item) => {
        // フェードアウト
        heroLink.style.opacity = '0';
        setTimeout(() => {
            const imageUrl = item.image_url ? item.image_url : "https://www.transparenttextures.com/patterns/cream-paper.png";
            heroBg.style.backgroundImage = `linear-gradient(to right, rgba(62, 76, 110, 0.4), transparent), url('${imageUrl}')`;
            heroCategory.textContent = item.category || "Top Article";
            heroTitle.textContent = item.title || "";
            heroDesc.textContent = item.content ? (item.content.length > 100 ? item.content.substring(0, 100) + '...' : item.content) : "詳細をチェックする";
            if (item.source_url) heroLink.href = item.source_url;

            // フェードイン
            heroLink.style.transition = 'opacity 0.8s ease-in-out';
            heroLink.style.opacity = '1';
        }, 800);
    };

    updateHeroDOM(items[currentIndex]);

    // 既存のインターバルがあればクリア
    if (heroIntervalId) clearInterval(heroIntervalId);

    // 複数件ある場合のみスライダー起動
    if (items.length > 1) {
        heroIntervalId = setInterval(() => {
            currentIndex = (currentIndex + 1) % items.length;
            updateHeroDOM(items[currentIndex]);
        }, 6000); // 6秒ごとに切り替え
    }
}

// ── レンダリング（サイドバー: ランキングまたはカレンダー） ──
function renderTrendingSeeds(items) {
    if (!trendingContainer) return;
    trendingContainer.innerHTML = "";

    // ログイン中の場合: お気に入りカレンダー
    if (authToken) {
        // カレンダー表示対象カテゴリ
        const calendarCategories = ["イベント", "コラボカフェ", "一番くじ", "予約"];
        // お気に入りかつ対象カテゴリのアイテムを抽出
        const favoriteEvents = items.filter(i => myFavorites.includes(i.title) && calendarCategories.includes(i.category));

        if (favoriteEvents.length === 0) {
            trendingContainer.innerHTML = `
                <div class="text-center py-6">
                    <span class="material-symbols-outlined text-stone-300 text-4xl mb-2">event_busy</span>
                    <p class="text-sm text-stone-400 font-medium">お気に入りアニメの<br/>直近イベントは見つかりませんでした</p>
                </div>
            `;
            // ヘッダータイトルの変更
            const tHeader = document.querySelector('aside h3');
            if (tHeader) tHeader.innerHTML = `<span class="material-symbols-outlined text-accent">edit_calendar</span> My Event Calendar`;
            return;
        }

        // 日付順（新しい/未来順）にソート (簡易的に文字列をソート、実際はDateパースが望ましい)
        favoriteEvents.sort((a, b) => new Date(b.date) - new Date(a.date));

        const tHeader = document.querySelector('aside h3');
        if (tHeader) tHeader.innerHTML = `<span class="material-symbols-outlined text-accent">edit_calendar</span> My Event Calendar`;

        favoriteEvents.slice(0, 5).forEach(item => {
            const dtStr = (item.date || "Unknown").substring(0, 10);
            const dtObj = new Date(dtStr);
            const month = isNaN(dtObj) ? "--" : dtObj.toLocaleString('en-US', { month: 'short' });
            const day = isNaN(dtObj) ? "--" : dtObj.getDate();

            const el = document.createElement("a");
            el.href = item.source_url;
            el.target = "_blank";
            el.className = "flex gap-4 group items-center p-3 rounded-2xl hover:bg-stone-50 transition-colors border border-transparent hover:border-stone-200 border-dashed border-[#e5dfd5]";

            el.innerHTML = `
                <div class="w-14 h-14 rounded-xl flex flex-col items-center justify-center shrink-0 border border-stone-200 bg-white">
                    <span class="text-[10px] text-accent font-bold uppercase tracking-wider">${month}</span>
                    <span class="text-lg font-black text-primary leading-none">${day}</span>
                </div>
                <div class="flex flex-col flex-1">
                    <span class="text-[10px] text-stone-400 font-bold uppercase tracking-widest mb-1 flex items-center gap-1">
                        <span class="w-2 h-2 rounded-full bg-accent inline-block"></span> ${escapeHtml(item.category || "Event")}
                    </span>
                    <h5 class="text-sm font-bold line-clamp-2 text-text-main group-hover:text-accent transition-colors leading-snug">${escapeHtml(item.title)}</h5>
                </div>
            `;
            trendingContainer.appendChild(el);
        });

    } else {
        // 未ログイン時の場合: 今までの Trending Seeds (スコア順トップ)
        const tHeader = document.querySelector('aside h3');
        if (tHeader) tHeader.innerHTML = `<span class="material-symbols-outlined text-accent">flare</span> Trending Seeds`;

        const topItems = [...items].sort((a, b) => b.total_score - a.total_score).slice(0, 3);

        topItems.forEach(item => {
            const imageUrl = item.image_url ? item.image_url : "https://www.transparenttextures.com/patterns/cream-paper.png";

            const el = document.createElement("a");
            el.href = item.source_url;
            el.target = "_blank";
            el.className = "flex gap-5 group items-center";

            el.innerHTML = `
                <div class="w-20 h-20 rounded-2xl bg-cover bg-center shrink-0 border border-stone-100 flex items-center justify-center overflow-hidden paper-shadow" style="background-image: url('${imageUrl}')">
                    ${!item.image_url ? '<span class="material-symbols-outlined text-stone-300 text-3xl">image</span>' : ''}
                </div>
                <div class="flex flex-col justify-center flex-1">
                    <h5 class="text-sm font-bold line-clamp-2 text-text-main group-hover:text-accent transition-colors leading-normal mb-1">${escapeHtml(item.title)}</h5>
                    <p class="text-[10px] text-stone-400 font-bold uppercase tracking-widest">${item.total_score} Score</p>
                </div>
            `;
            trendingContainer.appendChild(el);
        });
    }
}

// ── レンダリング（メイン記事） ──
function renderItems(items) {
    cardsContainer.innerHTML = "";

    if (items.length === 0) {
        emptyEl.classList.remove("hidden");
        return;
    }
    emptyEl.classList.add("hidden");

    items.forEach(item => {
        const card = document.createElement("div");
        card.className = "bg-card-bg rounded-[2rem] overflow-hidden border border-[#e5dfd5] group hover:border-accent/40 transition-all duration-500 paper-shadow flex flex-col h-full";

        // カテゴリバッジ表示用
        const catLabel = item.category || "News";

        // 画像
        const imageUrl = item.image_url ? item.image_url : "";
        const imageHtml = imageUrl
            ? `<img src="${imageUrl}" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-1000" alt="Thumbnail" loading="lazy" onerror="this.onerror=null; this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'100%\\' height=\\'100%\\'><rect width=\\'100%\\' height=\\'100%\\' fill=\\'%23fdfdfc\\'/><text x=\\'50%\\' y=\\'50%\\' dominant-baseline=\\'middle\\' text-anchor=\\'middle\\' fill=\\'%23cccccc\\' font-family=\\'Arial\\' font-size=\\'24\\'>No Image</text></svg>';">`
            : `<div class="w-full h-full bg-[#fdfdfc] flex items-center justify-center text-[#00704A] opacity-20"><span class="text-6xl">🌿</span></div>`;

        // 日付整形
        const dt = (item.date || "").substring(0, 10);
        let timeLabel = dt;
        // 本日なら時間表示に変換する簡易ロジック
        const todayStr = new Date().toISOString().substring(0, 10);
        if (dt === todayStr) timeLabel = "Today";

        card.innerHTML = `
            <div class="aspect-[4/3] relative overflow-hidden">
                ${imageHtml}
                <span class="absolute top-5 left-5 bg-white/90 backdrop-blur-sm text-primary text-[10px] font-bold tracking-widest px-4 py-1.5 rounded-full uppercase border border-primary/10">${catLabel}</span>
            </div>
            <div class="p-8 flex flex-col flex-1">
                <div class="flex items-center justify-between mb-3">
                    <span class="text-stone-400 text-xs font-medium flex items-center gap-2">
                        <span class="material-symbols-outlined text-[14px]">schedule</span> ${timeLabel}
                    </span>
                    <span class="text-xs font-bold ${item.total_score >= 80 ? 'text-accent' : 'text-stone-400'}">${item.total_score}pt</span>
                </div>
                
                <a href="${item.source_url}" target="_blank" class="block">
                    <h4 class="text-xl font-bold mb-4 line-clamp-2 leading-snug text-text-main group-hover:text-accent transition-colors">${escapeHtml(item.title)}</h4>
                </a>
                <p class="text-[15px] text-stone-500 font-light mb-8 line-clamp-3 leading-relaxed">${escapeHtml(item.content)}</p>
                
                <div class="mt-auto flex items-center justify-between pt-6 border-t border-[#f0ede6]">
                    <div class="flex items-center gap-2">
                        <button class="btn-fav w-8 h-8 rounded-full flex items-center justify-center border transition-colors ${myFavorites.includes(item.title) ? 'bg-rose-50 border-rose-200 text-rose-500' : 'bg-stone-50 border-stone-200 text-stone-400 hover:bg-stone-100'}" data-title="${escapeHtml(item.title)}">
                            <span class="material-symbols-outlined text-sm ${myFavorites.includes(item.title) ? 'fill-current' : ''}">favorite</span>
                        </button>
                        <button class="btn-share w-8 h-8 rounded-full flex items-center justify-center border bg-stone-50 border-stone-200 text-stone-400 hover:bg-stone-100 transition-colors" data-title="${escapeHtml(item.title)}" data-url="${escapeHtml(item.source_url)}">
                            <span class="material-symbols-outlined text-sm">share</span>
                        </button>
                    </div>
                    <a href="${item.source_url}" target="_blank" class="text-accent text-sm font-bold flex items-center gap-1.5 group/link">
                        Read Story <span class="material-symbols-outlined text-sm group-hover/link:translate-x-1 transition-transform">arrow_right_alt</span>
                    </a>
                </div>
            </div>
    `;
        cardsContainer.appendChild(card);
    });


    // Share Button Binding
    const shareBtns = cardsContainer.querySelectorAll(".btn-share");
    shareBtns.forEach(btn => {
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            shareItem(btn.dataset.title, btn.dataset.url);
        });
    });

    // Fav Button Binding
    const favBtns = cardsContainer.querySelectorAll(".btn-fav");
    favBtns.forEach(btn => {
        btn.addEventListener("click", async (e) => {
            e.stopPropagation();
            if (!authToken) {
                showToast("💬 お気に入り機能を使うにはSign Inしてください");
                authModal.classList.remove("hidden");
                return;
            }
            const title = btn.dataset.title;
            const isActive = myFavorites.includes(title);
            const method = isActive ? "DELETE" : "POST";

            try {
                const res = await fetch(`${API_BASE}/api/favorites`, {
                    method: method,
                    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${authToken}` },
                    body: JSON.stringify({ anime_title: title })
                });
                const json = await res.json();
                if (json.status === "ok") {
                    if (isActive) {
                        myFavorites = myFavorites.filter(t => t !== title);
                        showToast("💔 お気に入りを解除しました");

                        btn.classList.remove('bg-rose-50', 'border-rose-200', 'text-rose-500');
                        btn.classList.add('bg-stone-50', 'border-stone-200', 'text-stone-400', 'hover:bg-stone-100');
                        btn.querySelector('span').classList.remove('fill-current');
                    } else {
                        if (!myFavorites.includes(title)) myFavorites.push(title);
                        showToast("♥️ お気に入りに登録しました！新着時に通知します");

                        btn.classList.remove('bg-stone-50', 'border-stone-200', 'text-stone-400', 'hover:bg-stone-100');
                        btn.classList.add('bg-rose-50', 'border-rose-200', 'text-rose-500');
                        btn.querySelector('span').classList.add('fill-current');
                    }
                    // サイドバーのカレンダー（お気に入りリスト）も更新するため再レンダリング
                    renderTrendingSeeds(allItems);
                }
            } catch (err) {
                showToast("⚠️ 通信エラー");
            }
        });
    });
}

function getCategoryIcon(cat) {
    if (cat === "一番くじ") return "🎰";
    if (cat === "コラボカフェ") return "☕";
    if (cat === "グッズ") return "🛍";
    if (cat === "コラボ") return "🤝";
    if (cat === "予約") return "📅";
    if (cat === "イベント") return "🎪";
    return "🏷";
}
function getCategoryBadgeClass(cat) { return ""; } // 今回はCSS側の配色に合わせたシンプルなタグに統一

function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/[&<>"']/g, function (m) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#039;" }[m];
    });
}

// ── PWA Install ─────────────────────────────────────────────── //
let deferredPrompt;
window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredPrompt = e;
});

// ── Initialization ──
document.addEventListener("DOMContentLoaded", async () => {
    // OAuthコールバック後のURLパラメータ自動読み取り
    const urlParams = new URLSearchParams(window.location.search);
    const oauthToken = urlParams.get("token");
    const oauthEmail = urlParams.get("email");
    const oauthName = urlParams.get("name");
    const provider = urlParams.get("provider");
    const socialError = urlParams.get("social_error");

    if (oauthToken && oauthEmail) {
        // URLからトークンを取得してログイン完了状態に
        authToken = oauthToken;
        currentUser = decodeURIComponent(oauthEmail);
        currentDisplayName = oauthName ? decodeURIComponent(oauthName) : null;
        localStorage.setItem("token", authToken);
        localStorage.setItem("email", currentUser);
        if (currentDisplayName) localStorage.setItem("displayName", currentDisplayName);
        // URLをクリーンにする（リロードなし）
        window.history.replaceState({}, document.title, "/");
        updateHeaderAuth();
        const provName = provider ? provider.charAt(0).toUpperCase() + provider.slice(1) : "SNS";
        const welcomeName = currentDisplayName || currentUser.split("@")[0];
        showToast(`🎉 ${provName}アカウントでログインしました！ようこそ、${welcomeName}さん！`);
    } else if (socialError) {
        showToast(`⚠️ SNSログインに失敗しました: ${socialError}`);
        window.history.replaceState({}, document.title, "/");
    }

    setLoading(true);
    await fetchData();
    setLoading(false);

    // カテゴリフィルタのイベント
    if (filterBtns) {
        filterBtns.forEach(btn => {
            btn.addEventListener("click", () => {
                // UIのActive状態切り替え
                filterBtns.forEach(b => b.classList.remove("active"));
                btn.classList.add("active");

                // 状態更新
                currentCategory = btn.dataset.category || "all";

                // 検索モードかどうかに応じて表示対象を絞り込み
                let targetItems = allItems;
                if (isSearchMode) {
                    const q = searchInput ? searchInput.value.trim() : "";
                    if (q) {
                        targetItems = targetItems.filter(i => i.title.includes(q) || i.content.includes(q));
                    }
                }

                let filtered = applyFilters(targetItems);
                displayLimit = DISPLAY_STEP; // カテゴリ切替時に表示件数をリセット
                renderItems(filtered.slice(0, displayLimit));
                updateShowMoreBtn(filtered);
            });
        });
    }

    // 検索イベント
    const handleSearch = () => {
        const q = searchInput.value.trim();
        if (q) onSearch(q);
    };

    if (searchBtn) searchBtn.addEventListener("click", handleSearch);
    if (searchInput) {
        searchInput.addEventListener("keypress", (e) => {
            if (e.key === "Enter") handleSearch();
        });
    }

    // ── Auth Events ──
    const authStep1 = document.getElementById("auth-step-1");
    const authStep2 = document.getElementById("auth-step-2");
    const otpForm = document.getElementById("otp-form");
    const authOtp = document.getElementById("auth-otp");
    const authBackBtn = document.getElementById("auth-back-to-step1");
    // ソーシャルログイン用ボタン
    const btnLoginGoogle = document.getElementById("btn-login-google");
    const btnLoginLine = document.getElementById("btn-login-line");
    let pendingOtpEmail = "";
    let pendingVerificationMode = false; // 新規追加: 新規登録の本登録OTP認証か否か

    updateHeaderAuth();

    if (btnLoginOpen) {
        btnLoginOpen.addEventListener("click", () => {
            authModal.classList.remove("hidden");
            // モーダルを開くときは必ずStep1に戻す
            if (authStep1) authStep1.classList.remove("hidden");
            if (authStep2) authStep2.classList.add("hidden");
            authEmail.value = "";
            authPw.value = "";
            if (authOtp) authOtp.value = "";
        });
    }
    if (modalClose) {
        modalClose.addEventListener("click", () => {
            authModal.classList.add("hidden");
        });
    }
    if (authBackBtn) {
        authBackBtn.addEventListener("click", () => {
            authStep1.classList.remove("hidden");
            authStep2.classList.add("hidden");
            pendingOtpEmail = "";
            pendingVerificationMode = false;
        });
    }
    if (authToggle) {
        authToggle.addEventListener("click", () => {
            isLoginMode = !isLoginMode;
            if (isLoginMode) {
                authTitle.textContent = "ログイン";
                authSubmit.textContent = "ログイン";
                authToggle.textContent = "新規登録";
            } else {
                authTitle.textContent = "アカウント作成";
                authSubmit.textContent = "新規登録";
                authToggle.textContent = "ログイン";
            }
        });
    }

    // Step1: Email / Password Submit
    if (authForm) {
        authForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const email = authEmail.value.trim();
            const pw = authPw.value.trim();
            const endpoint = isLoginMode ? "/api/auth/login" : "/api/auth/register";

            try {
                const res = await fetch(`${API_BASE}${endpoint}`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ email: email, password: pw })
                });
                const json = await res.json();

                if (json.status === "2fa_required" || json.status === "verification_required") {
                    // 2段階認証へ進むか、または新規登録認証（メール送信モック）へ進む
                    pendingOtpEmail = json.email;
                    pendingVerificationMode = (json.status === "verification_required");
                    authStep1.classList.add("hidden");
                    authStep2.classList.remove("hidden");

                    // モードに応じてTitleとToastを少し変える
                    if (pendingVerificationMode) {
                        document.getElementById("auth-step-2-title").textContent = "メールの確認";
                        showToast("📧 認証メールを送信しました。受信トレイをご確認ください。");
                    } else {
                        document.getElementById("auth-step-2-title").textContent = "二段階認証";
                        showToast("📧 認証コードを送信しました");
                    }
                    if (authOtp) authOtp.focus();

                } else if (json.status === "ok") {
                    // 新規登録時などは即座にログイン成功
                    finishLogin(json.token, json.email);
                } else {
                    showToast(`⚠️ ${json.message}`);
                }
            } catch (err) {
                showToast("⚠️ 通信エラー");
            }
        });
    }

    // Step2: OTP Verify Submit
    if (otpForm) {
        otpForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const otp = authOtp.value.trim();
            if (!otp || !pendingOtpEmail) return;

            try {
                // モードに応じて呼び出すAPIを切り替える
                const verifyEndpoint = pendingVerificationMode ? "/api/auth/verify_registration" : "/api/auth/verify_otp";
                const res = await fetch(`${API_BASE}${verifyEndpoint}`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ email: pendingOtpEmail, otp: otp })
                });
                const json = await res.json();
                if (json.status === "ok") {
                    finishLogin(json.token, json.email);
                } else {
                    showToast(`⚠️ ${json.message}`);
                }
            } catch (err) {
                showToast("⚠️ 通信エラー");
            }
        });
    }

    // ソーシャル（本番/モックハイブリッド）ログイン処理
    // APIKeyが設定済みの場合は本物のOAuth匹面へ、未設定の場合はモックモード〜どちらもOK
    function handleSocialLogin(provider) {
        // サーバーへリダイレクト（モック or 本物OAuthはサーバー側で判定）
        window.location.href = `${API_BASE}/api/auth/social/login/${provider.toLowerCase()}`;
    }

    if (btnLoginGoogle) btnLoginGoogle.addEventListener("click", () => handleSocialLogin("google"));
    if (btnLoginLine) btnLoginLine.addEventListener("click", () => handleSocialLogin("line"));

    async function finishLogin(token, email, displayName) {
        authToken = token;
        currentUser = email;
        currentDisplayName = displayName || null;
        localStorage.setItem("token", authToken);
        localStorage.setItem("email", currentUser);
        if (currentDisplayName) localStorage.setItem("displayName", currentDisplayName);
        authModal.classList.add("hidden");
        updateHeaderAuth();
        const welcomeLabel = currentDisplayName || currentUser.split("@")[0];
        showToast(`👋 Welcome, ${welcomeLabel}!`);
        // お気に入り再取得＆再描画
        await fetchFavorites();
        currentItems = applyFilters(allItems);
        renderItems(!isSearchMode ? currentItems.slice(0, displayLimit) : currentItems);
        renderTrendingSeeds(allItems);
    }

    if (btnLogout) {
        btnLogout.addEventListener("click", () => {
            authToken = null;
            currentUser = null;
            currentDisplayName = null;
            myFavorites = [];
            localStorage.removeItem("token");
            localStorage.removeItem("email");
            localStorage.removeItem("displayName");
            updateHeaderAuth();

            // もしお気に入りタブ閲覧中ならAllに戻す
            if (currentCategory === "favorites") {
                currentCategory = "all";
                filterBtns.forEach(b => {
                    b.classList.remove("active");
                    if (b.dataset.category === "all") b.classList.add("active");
                });
            }

            showToast("👋 ログアウトしました");
            currentItems = applyFilters(allItems);
            renderItems(!isSearchMode ? currentItems.slice(0, displayLimit) : currentItems);
            renderTrendingSeeds(allItems);
        });
    }
});
