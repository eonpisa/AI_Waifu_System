import { useEffect, useState, useSyncExternalStore } from 'react'
import { ConversationClient } from './conversationClient'

export function useConversation() {
  const [client] = useState(() => new ConversationClient())
  const state = useSyncExternalStore(client.subscribe, client.getSnapshot)
  useEffect(() => { client.start(); return client.stop }, [client])
  return { ...state, send: client.send, end: client.end, dismissWarning: client.dismissWarning }
}
