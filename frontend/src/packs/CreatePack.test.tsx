import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { CreatePack } from "./CreatePack";
import { json } from "../api";

vi.mock("../api", () => ({ json: vi.fn() }));
const tasks = {
  run: async (_label: string, work: () => Promise<void>) => { await work(); },
  isRunning: () => false,
  reportError: vi.fn(),
};
const pack = { id: "p", name: "cats_by_bot", title: "Pack", status: "draft", count: 0, stickers: [] };

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  vi.mocked(json).mockImplementation(async (path) => path.includes("name-availability")
    ? { suffix: "_by_bot", max_length: 57, name: "cats_by_bot", available: true }
    : pack);
});
afterEach(() => { cleanup(); vi.useRealTimers(); });
async function tick(milliseconds: number) {
  await act(async () => { await vi.advanceTimersByTimeAsync(milliseconds); });
}

it("debounces name checks and includes a checked custom address on creation", async () => {
  const opened = vi.fn();
  render(<CreatePack tasks={tasks} onOpen={opened} />);
  fireEvent.change(screen.getByLabelText("Название набора"), { target: { value: "Pack" } });
  const input = screen.getByLabelText(/Своя ссылка/);
  fireEvent.change(input, { target: { value: "ca" } });
  await tick(200);
  fireEvent.change(input, { target: { value: "cats" } });
  await tick(349);
  expect(json).not.toHaveBeenCalled();
  expect((screen.getByRole("button", { name: "Создать набор" }) as HTMLButtonElement).disabled).toBe(true);
  await tick(1);
  expect(json).toHaveBeenCalledTimes(1);
  expect(json).toHaveBeenCalledWith("/api/packs/name-availability?short_name=cats");
  expect(screen.getByRole("status").textContent).toContain("https://t.me/addstickers/cats_by_bot");
  await act(async () => { fireEvent.submit(document.getElementById("pack-form")!); });
  expect(json).toHaveBeenCalledWith("/api/packs", { title: "Pack", source: null, short_name: "cats" });
  expect(opened).toHaveBeenCalled();
});

it("ignores stale availability results and blocks occupied or failed checks", async () => {
  let finish: (result: unknown) => void = () => {};
  vi.mocked(json).mockImplementation((path) => {
    if (path.endsWith("=cats")) return new Promise((resolve) => { finish = resolve; });
    return Promise.resolve({ name: "dogs_by_bot", suffix: "_by_bot", max_length: 57, available: false });
  });
  render(<CreatePack tasks={tasks} onOpen={vi.fn()} />);
  const input = screen.getByLabelText(/Своя ссылка/);
  fireEvent.change(input, { target: { value: "cats" } });
  await tick(350);
  fireEvent.change(input, { target: { value: "dogs" } });
  await tick(350);
  await act(async () => { finish({ name: "cats_by_bot", available: true }); });
  expect(screen.getByRole("status").textContent).toContain("уже занята");
  expect((screen.getByRole("button", { name: "Создать набор" }) as HTMLButtonElement).disabled).toBe(true);
  vi.mocked(json).mockRejectedValue(Error("Telegram недоступен"));
  fireEvent.change(input, { target: { value: "birds" } });
  await tick(350);
  expect(screen.getByRole("status").textContent).toContain("Telegram недоступен");
});

it("keeps an empty address optional for automatic generation", async () => {
  render(<CreatePack tasks={tasks} onOpen={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Название набора"), { target: { value: "Pack" } });
  await act(async () => { fireEvent.submit(document.getElementById("pack-form")!); });
  expect(json).toHaveBeenCalledWith("/api/packs", { title: "Pack", source: null, short_name: "" });
});
