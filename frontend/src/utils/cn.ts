/**
 * Class name utility similar to the shadcn/ui `cn` helper.
 */

type ClassValue = string | number | boolean | undefined | null | ClassValue[]

export function cn(...classes: ClassValue[]): string {
  return classes.flat().filter(Boolean).join(' ').trim()
}
