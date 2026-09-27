import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { Markdown } from "./Markdown";

it("met en évidence les renvois aux sources et les manques", () => {
  const { container } = render(
    <Markdown source="36 membres **formés** [S1][P2]. Lieu [source introuvable]. [À compléter : dates]" />,
  );
  expect([...container.querySelectorAll("sup")].map((s) => s.textContent)).toEqual(["S1", "P2"]);
  expect(screen.getByText("[source introuvable]").tagName).toBe("MARK");
  expect(screen.getByText("[À compléter : dates]").tagName).toBe("MARK");
  expect(screen.getByText("formés").tagName).toBe("STRONG");
});
