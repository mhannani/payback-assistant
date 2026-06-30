"use client";

import { useState } from "react";
import { useAssistChat } from "@/hooks/useAssistChat";
import { useDictation } from "@/hooks/useDictation";
import { ConversationScreen } from "./ConversationScreen";
import { ConsentDialog } from "./voice/ConsentDialog";

// Mixed DE/EN on purpose — the assistant handles both, so the chips show it.
const SUGGESTIONS = ["Günstige Windeln", "Organic pasta", "Shampoo für trockenes Haar", "Bluetooth headphones"];

/** The widget shell — opens straight into the conversation (header + messages + composer). No home
 * screen, no tab bar, no history: PAYBACK's /assist is stateless. Owns the /assist chat state, the
 * composer draft, and the voice-dictation session. Rendered full-bleed inside the embed iframe;
 * closing posts a message the embed script listens for. */
export function WidgetPanel() {
  const { messages, pending, send } = useAssistChat();
  const [draft, setDraft] = useState("");

  // Voice: session-local consent, the picked mic, and the dictation session (transcript → draft).
  const [hasConsent, setHasConsent] = useState(false);
  const [askingConsent, setAskingConsent] = useState(false);
  const [deviceId, setDeviceId] = useState<string | undefined>(undefined);
  const dictation = useDictation(setDraft, deviceId);

  const submit = (text: string) => {
    send(text);
    setDraft("");
  };

  const toggleMic = () => {
    if (dictation.recording) dictation.stop();
    else if (hasConsent) dictation.start();
    else setAskingConsent(true);
  };

  const grantConsent = () => {
    setHasConsent(true);
    setAskingConsent(false);
    dictation.start();
  };

  const close = () => window.parent?.postMessage("PAYBACK_CLOSE", "*");

  return (
    <div className="relative flex h-full w-full flex-col overflow-hidden bg-background">
      {askingConsent && (
        <ConsentDialog onGrant={grantConsent} onCancel={() => setAskingConsent(false)} />
      )}

      <ConversationScreen
        messages={messages}
        pending={pending}
        suggestions={SUGGESTIONS}
        onSuggestion={submit}
        onClose={close}
        value={draft}
        onChange={setDraft}
        onSend={() => submit(draft)}
        disabled={pending}
        micEnabled
        recording={dictation.recording}
        onMicToggle={toggleMic}
        selectedDeviceId={deviceId}
        onSelectDevice={setDeviceId}
        recordingStream={dictation.stream}
        interim={dictation.interim}
        onDictationDone={dictation.stop}
        onDictationCancel={dictation.cancel}
      />
    </div>
  );
}
