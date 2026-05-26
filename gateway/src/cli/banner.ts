import { resolveCommitHash } from "../infra/git-commit.js";
import { visibleWidth } from "../terminal/ansi.js";
import {
  decorativeEmoji,
  decorativePrefix,
  stripDecorativeEmojiForTerminal,
  supportsDecorativeEmoji,
  type DecorativeEmojiOptions,
} from "../terminal/decorative-emoji.js";
import { isRich, theme } from "../terminal/theme.js";
import { hasRootVersionAlias } from "./argv.js";
import { parseTaglineMode, readCliBannerTaglineMode } from "./banner-config-lite.js";
import { pickTagline, type TaglineMode, type TaglineOptions } from "./tagline.js";

type BannerOptions = TaglineOptions & {
  argv?: string[];
  commit?: string | null;
  columns?: number;
  isTty?: boolean;
  platform?: NodeJS.Platform;
  richTty?: boolean;
};

let bannerEmitted = false;

const graphemeSegmenter =
  typeof Intl !== "undefined" && "Segmenter" in Intl
    ? new Intl.Segmenter(undefined, { granularity: "grapheme" })
    : null;

function splitGraphemes(value: string): string[] {
  if (!graphemeSegmenter) {
    return Array.from(value);
  }
  try {
    return Array.from(graphemeSegmenter.segment(value), (seg) => seg.segment);
  } catch {
    return Array.from(value);
  }
}

const hasJsonFlag = (argv: string[]) =>
  argv.some((arg) => arg === "--json" || arg.startsWith("--json="));

const hasVersionFlag = (argv: string[]) =>
  argv.some((arg) => arg === "--version" || arg === "-V") || hasRootVersionAlias(argv);

function resolveTaglineMode(options: BannerOptions): TaglineMode | undefined {
  const explicit = parseTaglineMode(options.mode);
  if (explicit) {
    return explicit;
  }
  return readCliBannerTaglineMode(options.env);
}

function resolveEmojiOptions(options: BannerOptions): DecorativeEmojiOptions {
  return {
    ...(options.env ? { env: options.env } : {}),
    ...(options.isTty === undefined ? {} : { isTty: options.isTty }),
    ...(options.platform ? { platform: options.platform } : {}),
  };
}

export function formatCliBannerLine(version: string, options: BannerOptions = {}): string {
  const commit =
    options.commit ?? resolveCommitHash({ env: options.env, moduleUrl: import.meta.url });
  const commitLabel = commit ?? "unknown";
  const emojiOptions = resolveEmojiOptions(options);
  const tagline = stripDecorativeEmojiForTerminal(
    pickTagline({ ...options, mode: resolveTaglineMode(options) }),
    emojiOptions,
  );
  const rich = options.richTty ?? isRich();
  const title = decorativePrefix("🤖", "Parker", emojiOptions);
  const prefix = decorativeEmoji("🤖", emojiOptions);
  const indent = prefix ? `${prefix} ` : "";
  const columns = options.columns ?? process.stdout.columns ?? 120;
  const plainBaseLine = `${title} ${version} (${commitLabel})`;
  const plainFullLine = tagline ? `${plainBaseLine} — ${tagline}` : plainBaseLine;
  const fitsOnOneLine = visibleWidth(plainFullLine) <= columns;
  if (rich) {
    if (fitsOnOneLine) {
      if (!tagline) {
        return `${theme.heading(title)} ${theme.info(version)} ${theme.muted(`(${commitLabel})`)}`;
      }
      return `${theme.heading(title)} ${theme.info(version)} ${theme.muted(
        `(${commitLabel})`,
      )} ${theme.muted("—")} ${theme.accentDim(tagline)}`;
    }
    const line1 = `${theme.heading(title)} ${theme.info(version)} ${theme.muted(
      `(${commitLabel})`,
    )}`;
    if (!tagline) {
      return line1;
    }
    const line2 = `${" ".repeat(indent.length)}${theme.accentDim(tagline)}`;
    return `${line1}\n${line2}`;
  }
  if (fitsOnOneLine) {
    return plainFullLine;
  }
  const line1 = plainBaseLine;
  if (!tagline) {
    return line1;
  }
  const line2 = `${" ".repeat(indent.length)}${tagline}`;
  return `${line1}\n${line2}`;
}

const LOBSTER_ASCII_BODY = [
  "      ██████╗  █████╗ ██████╗ ██╗  ██╗███████╗██████╗ ",
  "      ██╔══██╗██╔══██╗██╔══██╗██║ ██╔╝██╔════╝██╔══██╗",
  "      ██████╔╝███████║██████╔╝█████╔╝ █████╗  ██████╔╝",
  "      ██╔═══╝ ██╔══██║██╔══██╗██╔═██╗ ██╔══╝  ██╔══██╗",
  "      ██║     ██║  ██║██║  ██║██║  ██╗███████╗██║  ██║",
  "      ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝",
];

function centerText(text: string, width: number): string {
  const pad = Math.max(0, width - visibleWidth(text));
  const left = Math.floor(pad / 2);
  const right = pad - left;
  return `${" ".repeat(left)}${text}${" ".repeat(right)}`;
}

function formatCliBannerArtLines(options: BannerOptions): string[] {
  const width = visibleWidth(LOBSTER_ASCII_BODY[0] ?? "");
  const emojiOptions = resolveEmojiOptions(options);
  const title = supportsDecorativeEmoji(emojiOptions) ? "🤖 PARKER 🤖" : "PARKER";
  return [...LOBSTER_ASCII_BODY, centerText(title, width), " "];
}

export function formatCliBannerArt(options: BannerOptions = {}): string {
  const rich = options.richTty ?? isRich();
  const lines = formatCliBannerArtLines(options);
  if (!rich) {
    return lines.join("\n");
  }

  const colorChar = (ch: string) => {
    if (ch === "█" || ch === "█" || ch === "█") {
      return theme.accentBright(ch);
    }
    if (ch === "░" || ch === "╚" || ch === "═" || ch === "▀" || ch === "▄" || ch === "╔" || ch === "╗") {
      return theme.accentDim(ch);
    }
    return theme.muted(ch);
  };

  const emojiOptions = resolveEmojiOptions(options);
  const icon = decorativeEmoji("🤖", emojiOptions);
  const colored = lines.map((line) => {
    if (line.includes("PARKER")) {
      if (!icon) {
        return theme.info(centerText("PARKER", visibleWidth(line)));
      }
      return (
        theme.muted("                  ") +
        theme.accent(icon) +
        theme.info(" PARKER ") +
        theme.accent(icon)
      );
    }
    return splitGraphemes(line).map(colorChar).join("");
  });

  return colored.join("\n");
}

export function emitCliBanner(version: string, options: BannerOptions = {}) {
  if (bannerEmitted) {
    return;
  }
  const argv = options.argv ?? process.argv;
  if (!process.stdout.isTTY) {
    return;
  }
  if (hasJsonFlag(argv)) {
    return;
  }
  if (hasVersionFlag(argv)) {
    return;
  }
  const line = formatCliBannerLine(version, options);
  process.stdout.write(`\n${line}\n\n`);
  bannerEmitted = true;
}

export function hasEmittedCliBanner(): boolean {
  return bannerEmitted;
}
