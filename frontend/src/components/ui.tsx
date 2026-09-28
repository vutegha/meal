/**
 * Composants de formulaire de l'application, assemblés à partir des primitives shadcn/ui de
 * `components/ui/` (mêmes conventions : `cn`, variantes `cva`).
 */
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { useId } from "react";

import { Button as BaseButton, type ButtonProps } from "./ui/button";
import { Card as BaseCard, CardTitle } from "./ui/card";
import { Input, NativeSelect } from "./ui/input";
import { Label } from "./ui/label";

export { Badge } from "./ui/badge";

export function Field({
  label,
  hint,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  const id = useId();
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} {...props} />
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export function Select({
  label,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string; children: ReactNode }) {
  const id = useId();
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      <NativeSelect id={id} {...props}>
        {children}
      </NativeSelect>
    </div>
  );
}

const VARIANTS = { primary: "default", ghost: "ghost", danger: "destructive" } as const;

export function Button({
  variant = "primary",
  ...props
}: Omit<ButtonProps, "variant"> & { variant?: keyof typeof VARIANTS }) {
  return <BaseButton variant={VARIANTS[variant]} {...props} />;
}

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <BaseCard>
      {title && <CardTitle>{title}</CardTitle>}
      {children}
    </BaseCard>
  );
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="text-sm text-red-700">
      {error instanceof Error ? error.message : String(error)}
    </p>
  );
}
