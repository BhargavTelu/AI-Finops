"use client"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

interface ConfirmDialogProps {
  open: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  description: string
  /** Label for the confirm button (default: "Confirm") */
  confirmLabel?: string
  /** Label for the cancel button (default: "Cancel") */
  cancelLabel?: string
  /**
   * "destructive" — red confirm button (for delete/revoke/remove actions).
   * "default"     — primary blue confirm button.
   */
  variant?: "destructive" | "default"
  /** Disable confirm button while an async action is in flight */
  isLoading?: boolean
}

/**
 * Re-usable confirmation dialog for all destructive or irreversible actions.
 * Cancel is always visually prominent (safe choice). Confirm is secondary.
 *
 * Usage:
 *   <ConfirmDialog
 *     open={showRevoke}
 *     onClose={() => setShowRevoke(false)}
 *     onConfirm={handleRevoke}
 *     title="Revoke API key"
 *     description="This key will stop syncing immediately and cannot be recovered."
 *     confirmLabel="Revoke key"
 *     variant="destructive"
 *   />
 */
export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "default",
  isLoading = false,
}: ConfirmDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <DialogFooter>
          {/* Cancel is always the first / visually safe option */}
          <Button variant="outline" onClick={onClose} disabled={isLoading}>
            {cancelLabel}
          </Button>
          <Button
            variant={variant === "destructive" ? "destructive" : "default"}
            onClick={onConfirm}
            disabled={isLoading}
          >
            {isLoading ? "Processing…" : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
