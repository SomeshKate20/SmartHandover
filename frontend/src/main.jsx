import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider } from '@clerk/react'
import App from './App'
import './App.css'

const clerkPublishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {clerkPublishableKey
      ? <ClerkProvider publishableKey={clerkPublishableKey}><App /></ClerkProvider>
      : <App authEnabled={false} />}
  </StrictMode>,
)
