import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios from 'axios'
import { authService } from '../auth'

vi.mock('axios', () => {
  return {
    default: {
      get: vi.fn(),
      post: vi.fn(),
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() }
      },
      defaults: {
        headers: { common: {} }
      }
    }
  }
})

// Mock localStorage
let store: Record<string, string> = {}
const mockLocalStorage = {
  getItem: (key: string) => store[key] || null,
  setItem: (key: string, value: string) => { store[key] = value.toString() },
  removeItem: (key: string) => { delete store[key] },
  clear: () => { store = {} }
}
Object.defineProperty(global, 'localStorage', {
  value: mockLocalStorage
})

describe('authService', () => {
  beforeEach(() => {
    mockLocalStorage.clear()
    vi.clearAllMocks()
  })

  it('doit appeler login et sauvegarder le token', async () => {
    (axios.post as any).mockResolvedValueOnce({
      data: { access_token: 'fake-token-123' }
    });
    (axios.get as any).mockResolvedValueOnce({
      data: { id: 1, email: 'test@test.com', access_token: 'fake-token-123' }
    });

    await authService.login('test@test.com', 'password')
    expect(localStorage.getItem('access_token')).toBe('fake-token-123')
    expect(authService.state.isAuthenticated).toBe(true)
    expect(authService.state.user?.email).toBe('test@test.com')
  })

  it('doit appeler logout et nettoyer le token', async () => {
    localStorage.setItem('access_token', 'token')
    
    // Prévention rechargement
    const oldLoc = window.location
    delete (window as any).location
    window.location = { ...oldLoc, href: '' } as any

    (axios.post as any).mockResolvedValueOnce({})

    await authService.logout()
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(authService.state.isAuthenticated).toBe(false)
    
    window.location = oldLoc
  })
  
  it('doit vérifier l\'authentification avec succès', async () => {
    (axios.get as any).mockResolvedValueOnce({
      data: { id: 2, username: 'alice' }
    });
    await authService.checkAuth()
    expect(authService.state.isAuthenticated).toBe(true)
    expect(authService.state.user?.username).toBe('alice')
  })
  
  it('doit gérer l\'échec de checkAuth (déconnexion)', async () => {
    (axios.get as any).mockRejectedValueOnce(new Error('Network error'));
    await authService.checkAuth()
    expect(authService.state.isAuthenticated).toBe(false)
    expect(authService.state.user).toBeNull()
  })
})
