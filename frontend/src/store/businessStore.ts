import { create } from 'zustand';
import type { Business } from '@/types';

interface BusinessState {
  currentBusiness: Business | null;
  setCurrentBusiness: (business: Business | null) => void;
}

export const useBusinessStore = create<BusinessState>((set) => ({
  currentBusiness: null,
  setCurrentBusiness: (business) => set({ currentBusiness: business }),
}));
