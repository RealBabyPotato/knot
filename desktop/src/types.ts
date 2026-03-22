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

export type KnotDetailMode = "minimal" | "enriched";

export type KnotProcessRequest = {
  path: string;
  title?: string;
  content: string;
  outputPath?: string;
  outputFolder?: string;
  detailMode?: KnotDetailMode;
};

export type ProcessResponse = {
  mode?: string;
  path?: string;
  notePath?: string;
  title?: string;
  content?: string;
  updatedAt?: string | number;
  status?: string;
  relatedLinks?: string[];
  outputFolder?: string;
};

export type WorkspaceSettings = {
  baseDir: string;
  vaultDir: string;
  inboxDir: string;
  provider: string;
  detailMode: string;
};
