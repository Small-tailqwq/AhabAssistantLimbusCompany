----------------------------- MODULE MirrorRecovery -----------------------------
EXTENDS Naturals
VARIABLES fault, phase, payments, receipts, entered, restarts, settled, rotated, persisted
vars == <<fault, phase, payments, receipts, entered, restarts, settled, rotated, persisted>>
Init == /\ fault \in {"none", "restart", "blocked", "cancel"} /\ phase = "Settlement"
        /\ payments = 0 /\ receipts = 0 /\ entered = 0 /\ restarts = 0
        /\ settled = FALSE /\ rotated = FALSE /\ persisted = FALSE
SubmitModules == /\ phase = "Settlement" /\ phase' = "Receipt" /\ payments' = payments + 1
                 /\ UNCHANGED <<fault, receipts, entered, restarts, settled, rotated, persisted>>
InputBlocked == /\ phase = "Receipt" /\ fault = "blocked" /\ phase' = "InputBlocked"
                /\ UNCHANGED <<fault, payments, receipts, entered, restarts, settled, rotated, persisted>>
WaitForInputRecovery == /\ phase = "InputBlocked" /\ phase' = "RetryEntryWithReceipt"
                        /\ UNCHANGED <<fault, payments, receipts, entered, restarts, settled, rotated, persisted>>
EntryCannotRecognizeReceipt == /\ phase = "RetryEntryWithReceipt" /\ phase' = "Failed"
                              /\ UNCHANGED <<fault, payments, receipts, entered, restarts, settled, rotated, persisted>>
ConfirmReceipt == /\ phase = "Receipt" /\ fault # "blocked" /\ phase' = "AwaitEntrance"
                  /\ receipts' = receipts + 1
                  /\ UNCHANGED <<fault, payments, entered, restarts, settled, rotated, persisted>>
ObserveFatalPage == /\ phase = "AwaitEntrance" /\ fault = "restart" /\ restarts = 0
                    /\ phase' = "FatalObserved"
                    /\ UNCHANGED <<fault, payments, receipts, entered, restarts, settled, rotated, persisted>>
RestartGame == /\ phase = "FatalObserved" /\ phase' = "Restarted" /\ restarts' = 1
               /\ UNCHANGED <<fault, payments, receipts, entered, settled, rotated, persisted>>
ObserveHomeAfterRestart == /\ phase = "Restarted" /\ phase' = "HomeAfterRestart"
                          /\ UNCHANGED <<fault, payments, receipts, entered, restarts, settled, rotated, persisted>>
NavigateFromHome == /\ phase = "HomeAfterRestart" /\ phase' = "MirrorHub"
                    /\ UNCHANGED <<fault, payments, receipts, entered, restarts, settled, rotated, persisted>>
NavigateToEntry == /\ phase = "MirrorHub" /\ phase' = "FreshEntry"
                   /\ UNCHANGED <<fault, payments, receipts, entered, restarts, settled, rotated, persisted>>
EnterAnotherDungeon == /\ phase = "FreshEntry" /\ phase' = "SecondDungeon" /\ entered' = entered + 1
                       /\ UNCHANGED <<fault, payments, receipts, restarts, settled, rotated, persisted>>
CompleteAnotherDungeon == /\ phase = "SecondDungeon" /\ phase' = "Settlement"
                          /\ UNCHANGED <<fault, payments, receipts, entered, restarts, settled, rotated, persisted>>
ObserveEntrance == /\ phase = "AwaitEntrance" /\ (fault # "restart" \/ restarts = 1)
                   /\ phase' = "Claimed" /\ settled' = TRUE
                   /\ UNCHANGED <<fault, payments, receipts, entered, restarts, rotated, persisted>>
RotateQueue == /\ phase = "Claimed" /\ phase' = "SavingQueue" /\ rotated' = TRUE
               /\ UNCHANGED <<fault, payments, receipts, entered, restarts, settled, persisted>>
SaveQueue == /\ phase = "SavingQueue" /\ fault # "cancel" /\ phase' = "Done" /\ persisted' = TRUE
             /\ UNCHANGED <<fault, payments, receipts, entered, restarts, settled, rotated>>
CancelBeforeSave == /\ phase = "SavingQueue" /\ fault = "cancel" /\ phase' = "StopRequested"
                    /\ UNCHANGED <<fault, payments, receipts, entered, restarts, settled, rotated, persisted>>
RejectCanceledSave == /\ phase = "StopRequested" /\ phase' = "Cancelled"
                      /\ UNCHANGED <<fault, payments, receipts, entered, restarts, settled, rotated, persisted>>
Done == /\ phase \in {"Done", "Failed", "Cancelled"} /\ UNCHANGED vars
Next == SubmitModules \/ InputBlocked \/ WaitForInputRecovery \/ EntryCannotRecognizeReceipt \/ ConfirmReceipt
        \/ ObserveFatalPage \/ RestartGame \/ ObserveHomeAfterRestart \/ NavigateFromHome \/ NavigateToEntry
        \/ EnterAnotherDungeon \/ CompleteAnotherDungeon \/ ObserveEntrance \/ RotateQueue
        \/ SaveQueue \/ CancelBeforeSave \/ RejectCanceledSave \/ Done
TypeOK == /\ fault \in {"none", "restart", "blocked", "cancel"}
          /\ phase \in {"Settlement", "Receipt", "InputBlocked", "RetryEntryWithReceipt", "Failed", "AwaitEntrance",
                        "FatalObserved", "Restarted", "HomeAfterRestart", "MirrorHub", "FreshEntry", "SecondDungeon",
                        "Claimed", "SavingQueue", "StopRequested", "Done", "Cancelled"}
          /\ payments \in 0..2 /\ receipts \in 0..2 /\ entered \in 0..1 /\ restarts \in 0..1
          /\ settled \in BOOLEAN /\ rotated \in BOOLEAN /\ persisted \in BOOLEAN
NoUnplannedRound == entered = 0
NoExtraPayment == payments <= 1
TransientBlockKeepsReceiptRecoverable == ~(phase = "Failed" /\ fault = "blocked")
CompletedClaimKeepsRotation == (phase \in {"Done", "Failed", "Cancelled"} /\ settled) => persisted
RotationNeedsVerifiedClaim == rotated => (settled /\ receipts > 0)
=============================================================================
