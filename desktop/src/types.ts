export type NoteSummary = {
  path: string;
  title: string;
  preview?: string;
  updatedAt?: string | number;
};

export type NoteDocument = {
  path: string;
  title: string;
  content: string;
  updatedAt?: string | number;
};

export type KnotStatus = {
  healthy: boolean;
  message: string;
};

export type ProcessResponse = {
  path?: string;
  title?: string;
  content?: string;
  updatedAt?: string | number;
  status?: string;
};

export type WorkspaceSettings = {
  baseDir: string;
  vaultDir: string;
  inboxDir: string;
  provider: string;
  detailMode: string;
};
