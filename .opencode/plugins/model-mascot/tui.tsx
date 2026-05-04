// @ts-nocheck
/** @jsxImportSource @opentui/solid */
import { createMemo, createSignal, For, Show } from "solid-js"

const MASCOTS = {
  claude: {
    name: "Claude",
    art: [
      "⠀⠀⢰⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⣶⡆",
      "⠀⠀⢸⣿⣿⠿⢿⣿⣿⣿⣿⣿⣿⣿⡿⠿⣿⣿⡇",
      "⠀⠀⢸⣿⣿⠀⢸⣿⣿⣿⣿⣿⣿⣿⡇⠀⣿⣿⡇",
      "⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿",
      "⠛⠛⢻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡟⠛⠛",
      "⠀⠀⠸⠿⣿⠿⢿⣿⠿⠿⠿⠿⠿⣿⡿⠿⣿⠿⠇⠀⠀",
      "⠀⠀⠀⠀⣿⠀⢸⣿⠀⠀⠀⠀⠀⣿⡇⠀⣿⠀⠀⠀⠀",
      "⠀⠀⠀⠀⠉⠀⠈⠉⠀⠀⠀⠀⠀⠉⠁⠀⠉⠀⠀⠀⠀",
    ],
  },
  gpt: {
    name: "GPT",
    art: [
      "⠀⠀⠀⠀⠀⣠⣴⠶⠶⠶⣦⣄⠀⠀⠀⠀",
      "⠀⠀⠀⠀⣴⠟⠁⠀⢀⣠⣾⠟⠛⠛⠻⣶⣄",
      "⠀⣠⡾⠟⣿⠀⢠⡾⠟⠉⠀⣠⣤⣀⠀⠈⢻⡆",
      "⢰⡟⠀⠀⣿⠀⢸⣇⣠⠶⣟⡁⠈⠛⠷⣦⣼⡇",
      "⢸⡇⠀⠀⣿⠀⢸⡏⠁⠀⠈⢹⡷⣤⣀⠈⠙⣷⡀",
      "⠈⢿⣄⡀⠈⠛⢾⣇⡀⠀⢀⣸⡇⠀⣿⠀⠀⢸⡇",
      "⠀⢸⡟⠻⢶⣤⡀⢈⣽⠶⠋⢹⡇⠀⣿⠀⠀⣼⠇",
      "⠀⠸⣧⡀⠀⠉⠛⠋⠀⣀⣴⡾⠃⠀⣿⣴⡾⠋",
      "⠀⠀⠙⠿⣦⣤⣤⣴⡿⠋⠁⠀⢀⣴⠟⠀⠀",
      "⠀⠀⠀⠀⠀⠀⠀⠙⠻⠶⠶⠶⠟⠋⠀⠀⠀⠀",
    ],
  },
  gemini: {
    name: "Gemini",
    art: [
      "⠀⠀⠀⠀⠀⠀⢀⣶⡀⠀⠀⠀⠀⠀⠀⠀",
      "⠀⠀⠀⠀⠀⢀⣾⣿⣷⡀⠀⠀⠀⠀⠀⠀",
      "⠀⠀⠀⣀⣴⣿⣿⣿⣿⣿⣦⣀⠀⠀⠀⠀",
      "⠠⠶⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠶⠄",
      "⠀⠀⠀⠉⠻⣿⣿⣿⣿⣿⠟⠉⠀⠀⠀⠀",
      "⠀⠀⠀⠀⠀⠈⢿⣿⡿⠁⠀⠀⠀⠀⠀⠀",
      "⠀⠀⠀⠀⠀⠀⠈⠿⠁⠀⠀⠀⠀⠀⠀⠀",
    ],
  },
  deepseek: {
    name: "DeepSeek",
    art: [
      "⠀⢀⣠⣤⣤⣴⣶⡆⠀⠀⣧⣀⠀⣀⡄",
      "⢠⣿⣿⣿⣿⣿⣿⣿⣦⡀⠻⣿⣿⡿⠃",
      "⣿⠉⠉⠙⠻⣿⣿⡟⡛⢿⣶⣿⠇⠀⠀",
      "⢿⡆⠀⠀⠀⠈⢻⣿⣧⣬⣿⡟⠀⠀⠀",
      "⠘⢿⣆⠀⠀⣤⡀⠻⣿⣿⡟⠁⠀⠀⠀",
      "⠀⠀⠙⠿⣶⣿⣿⣶⠞⠛⠛⠃⠀⠀⠀",
    ],
  },
  mistral: {
    name: "Mistral",
    art: [
      "   ༄  ༄  ༄   ",
      "  ╭────────╮  ",
      "  │ ◓    ◓ │  ",
      "  │   ──   │  ",
      "  ╰────────╯  ",
      "   ༄  ༄  ༄   ",
    ],
  },
}

const FALLBACK = {
  name: "CodeBot",
  art: [
    "  ╭────────╮  ",
    "  │ •    • │  ",
    "  │   ──   │  ",
    "  ╰───┬┬───╯  ",
    "      ┴┴      ",
  ],
}

const HOME = {
  art: [
    "  ╭────────╮  ",
    "  │ ^    ^ │  ",
    "  │   ‿‿   │  ",
    "  ╰────────╯  ",
    "     zzZZZ    ",
  ],
}

const MODEL_RULES = [
  { key: "claude", test: (id) => id.includes("claude") },
  { key: "gpt", test: (id) => id.includes("gpt") || id.startsWith("o1") || id.startsWith("o3") },
  { key: "gemini", test: (id) => id.includes("gemini") },
  { key: "deepseek", test: (id) => id.includes("deepseek") },
  { key: "mistral", test: (id) => id.includes("mistral") },
]

// ─── helpers ────────────────────────────────────────────────

function fmt(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M"
  if (n >= 10_000) return Math.round(n / 1_000) + "K"
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K"
  return String(n)
}

function bar(ratio, width) {
  const r = Math.max(0, Math.min(1, ratio))
  const n = Math.round(r * width)
  return "\u2588".repeat(n) + "\u2591".repeat(width - n)
}

function classifyModel(modelID) {
  if (!modelID || typeof modelID !== "string") return null
  const id = modelID.toLowerCase()
  for (const rule of MODEL_RULES) {
    if (rule.test(id)) return rule.key
  }
  return null
}

function detectModel(api, sessionId) {
  if (!sessionId) return null
  const messages = api.state.session.messages(sessionId)
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i]
    if (msg.role !== "assistant") continue
    if (msg.modelID) {
      const key = classifyModel(msg.modelID)
      if (key) return key
    }
  }
  return null
}

// ─── cumulative token stats (all messages) ────────────────

function getTokenStats(api, sessionId) {
  if (!sessionId) return null
  const messages = api.state.session.messages(sessionId)

  let totalInput = 0
  let totalOutput = 0
  let totalCache = 0
  let totalCost = 0
  let lastModelID = null
  let latestTps = 0

  for (const msg of messages) {
    if (msg.role !== "assistant") continue
    if (!msg.modelID) continue
    lastModelID = msg.modelID
    totalInput = (msg.tokens?.total || msg.tokens?.input) ?? 0
    totalOutput += msg.tokens?.output ?? 0
    totalCache = msg.tokens?.cache?.read ?? 0
    totalCost += msg.cost ?? 0
    const outTokens = (msg.tokens?.output ?? 0) + (msg.tokens?.reasoning ?? 0)
    if (outTokens > 0 && msg.time?.completed && msg.time?.created) {
      const dur = msg.time.completed - msg.time.created
      if (dur > 0) latestTps = outTokens / (dur / 1000)
    }
  }

  if (!lastModelID) return null

  let contextLimit = 0
  let outputLimit = 0
  for (const provider of api.state.provider ?? []) {
    const model = provider.models?.[lastModelID]
    if (model) {
      contextLimit = model.limit?.context ?? 0
      outputLimit = model.limit?.output ?? 0
      break
    }
  }

  return {
    totalInput,
    totalOutput,
    totalCache,
    totalCost,
    contextLimit,
    outputLimit,
    contextRatio: contextLimit > 0 ? Math.min(1, totalInput / contextLimit) : 0,
    outputRatio: outputLimit > 0 ? Math.min(1, totalOutput / outputLimit) : 0,
    cacheRatio: totalInput > 0 ? Math.min(1, totalCache / totalInput) : 0,
    latestTps,
    hasData: totalInput > 0 || totalOutput > 0,
  }
}

// ─── TPS/TTFT tracker (adapted from oc-tps) ──────────────

const STREAM_WINDOW_MS = 5_000

function estimateStreamTokens(delta) {
  return Math.max(1, Math.ceil(Buffer.byteLength(delta, "utf8") / 5))
}

function fmtTps(value) {
  if (!Number.isFinite(value) || value <= 0) return "-"
  if (value >= 100) return `${Math.round(value)}`
  if (value >= 10) return `${value.toFixed(1)}`
  return `${value.toFixed(2)}`
}

function fmtTtft(value) {
  if (!Number.isFinite(value) || value < 0) return "-"
  return `${value.toFixed(1)}s`
}

// ─── components ─────────────────────────────────────────────

function SideCharacter(props) {
  const hasSession = () => !!props.sessionId

  const mascotKey = createMemo(() => detectModel(props.api, props.sessionId))
  const mascot = createMemo(() => MASCOTS[mascotKey()] ?? null)

  const display = createMemo(() => {
    if (!hasSession()) return HOME
    return mascot() ?? FALLBACK
  })

  const stats = createMemo(() => getTokenStats(props.api, props.sessionId))
  const t = () => props.theme
  const artColor = createMemo(() => mascotKey() === "deepseek" ? t().primary : t().textMuted)

  const timing = createMemo(() => {
    props.version()
    const live = props.tracker?.latestMsgBySession[props.sessionId]
    if (live) return { tps: fmtTps(live.tps), ttft: fmtTtft(live.ttft) }
    const s = stats()
    if (s?.latestTps > 0) return { tps: fmtTps(s.latestTps), ttft: "-" }
    return null
  })

  return (
    <box paddingLeft={1} paddingRight={1}>
      <box flexDirection="column">
        <box alignItems="center" flexDirection="column">
          <For each={display().art}>
            {(line) => (
              <text fg={artColor()} selectable={false}>
                {line}
              </text>
            )}
          </For>
          <Show when={mascot()}>
            <text fg={t().primary} selectable={false}>
              ── {mascot().name} ──
            </text>
          </Show>
        </box>

        <Show when={stats()?.hasData}>
          {(() => {
            const s = stats()
            const barW = Math.max(6, (props.barWidth ?? 10))

            const ctxColor = s.contextRatio > 0.9 ? t().error
              : s.contextRatio > 0.7 ? t().warning
              : t().primary

            return (
              <box flexDirection="column" paddingTop={1}>
                <Show when={s.contextLimit > 0}>
                  <text>
                    <span fg={t().textMuted}>CTX </span>
                    <span fg={ctxColor}>[{bar(s.contextRatio, barW)}]</span>
                    <span fg={t().text}> {Math.round(s.contextRatio * 100)}%</span>
                  </text>
                  <text fg={t().textMuted}>
                    {fmt(s.totalInput)} / {fmt(s.contextLimit)}
                  </text>
                </Show>
                <Show when={s.outputLimit > 0}>
                  <text>
                    <span fg={t().textMuted}>OUT </span>
                    <span fg={t().primary}>[{bar(s.outputRatio, barW)}]</span>
                    <span fg={t().text}> {Math.round(s.outputRatio * 100)}%</span>
                  </text>
                  <text fg={t().textMuted}>
                    {fmt(s.totalOutput)} / {fmt(s.outputLimit)}
                  </text>
                </Show>
                <Show when={s.totalInput > 0}>
                  <text>
                    <span fg={t().textMuted}>CSH </span>
                    <span fg={t().success}>[{bar(s.cacheRatio, barW)}]</span>
                    <span fg={t().text}> {Math.round(s.cacheRatio * 100)}%</span>
                  </text>
                </Show>
                <Show when={s.totalCost > 0}>
                  <text>
                    <span fg={t().textMuted}>CAPS </span>
                    <span fg={t().warning}>
                      ${s.totalCost < 1 ? s.totalCost.toFixed(4) : s.totalCost.toFixed(2)}
                    </span>
                  </text>
                </Show>
                <Show when={timing()}>
                  <text fg={t().textMuted}>
                    TPS {timing().tps} | TTFT {timing().ttft}
                  </text>
                </Show>
              </box>
            )
          })()}
        </Show>
      </box>
    </box>
  )
}

// ─── plugin entry ───────────────────────────────────────────

const id = "model-mascot"

const tui = async (api, _options) => {
  await api.plugins.deactivate("internal:sidebar-context").catch(() => {})

  api.lifecycle.onDispose(async () => {
    await api.plugins.activate("internal:sidebar-context").catch(() => {})
  })

  const tracker = {
    streamSamplesBySession: {},
    messageTimingByID: {},
    sessionAverageByID: {},
    latestMsgBySession: {},
  }

  const [version, setVersion] = createSignal(0)
  const [clock, setClock] = createSignal(Date.now())

  const bump = () => setVersion((v) => v + 1)

  const onDelta = api.event.on("message.part.delta", (evt) => {
    if (evt.properties.field !== "text") return
    const now = Date.now()
    const samples = tracker.streamSamplesBySession[evt.properties.sessionID] ?? []
    tracker.streamSamplesBySession[evt.properties.sessionID] = [
      ...samples.filter((s) => now - s.at <= STREAM_WINDOW_MS),
      { at: now, tokens: estimateStreamTokens(evt.properties.delta) },
    ]
    const timing = tracker.messageTimingByID[evt.properties.messageID]
    if (timing) {
      tracker.messageTimingByID[evt.properties.messageID] = timing.firstTokenAt
        ? { ...timing, lastTokenAt: now }
        : { ...timing, firstResponseAt: timing.firstResponseAt ?? now, firstTokenAt: now, lastTokenAt: now }
    }
    bump()
  })

  const onMessage = api.event.on("message.updated", (evt) => {
    if (evt.properties.info.role !== "assistant") return

    if (!evt.properties.info.time.completed) {
      tracker.messageTimingByID[evt.properties.info.id] = {
        sessionID: evt.properties.sessionID,
        requestStartAt: evt.properties.info.time.created,
        firstTokenAt: undefined,
        lastTokenAt: undefined,
      }
      bump()
      return
    }

    const timing = tracker.messageTimingByID[evt.properties.info.id]
    if (timing?.sessionID === evt.properties.sessionID && typeof timing.firstTokenAt === "number") {
      const totalTokens = (evt.properties.info.tokens.output ?? 0) + (evt.properties.info.tokens.reasoning ?? 0)
      const durationMs = Math.max(timing.lastTokenAt - timing.firstTokenAt, 1)
      const ttftMs = Math.max(timing.firstTokenAt - timing.requestStartAt, 0)
      if (totalTokens > 0) {
        const totals = tracker.sessionAverageByID[evt.properties.sessionID] ?? {
          totalTokens: 0, totalDurationMs: 0, totalTtftMs: 0, messageCount: 0,
        }
        tracker.sessionAverageByID[evt.properties.sessionID] = {
          totalTokens: totals.totalTokens + totalTokens,
          totalDurationMs: totals.totalDurationMs + durationMs,
          totalTtftMs: totals.totalTtftMs + ttftMs,
          messageCount: totals.messageCount + 1,
        }
        tracker.latestMsgBySession[evt.properties.sessionID] = {
          tps: totalTokens / (durationMs / 1000),
          ttft: ttftMs / 1000,
        }
      }
    }
    delete tracker.messageTimingByID[evt.properties.info.id]
    bump()
  })

  const timer = setInterval(() => {
    setClock(Date.now())
    const now = Date.now()
    let changed = false
    for (const [sid, samples] of Object.entries(tracker.streamSamplesBySession)) {
      const next = samples.filter((s) => now - s.at <= STREAM_WINDOW_MS)
      if (next.length !== samples.length) {
        changed = true
        if (next.length > 0) tracker.streamSamplesBySession[sid] = next
        else delete tracker.streamSamplesBySession[sid]
      }
    }
    if (changed) bump()
  }, 1000)

  api.lifecycle.onDispose(() => {
    onDelta()
    onMessage()
    clearInterval(timer)
  })

  api.slots.register({
    order: 60,
    slots: {
      sidebar_content(ctx, input) {
        return (
          <SideCharacter
            api={api}
            sessionId={input?.session_id}
            theme={ctx.theme.current}
            tracker={tracker}
            version={version}
            clock={clock}
            barWidth={12}
          />
        )
      },
    },
  })
}

const plugin = { id, tui }
export default plugin
