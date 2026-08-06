export interface User {
  uid: string;
  email: string;
  displayName?: string;
  nativeLanguage: string;
  targetLanguage: string;
  createdAt: Date;
  lastActive: Date;
}
