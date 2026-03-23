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
export type KnotOutputMode = "single_note" | "linked_tree";

export type KnotProcessRequest = {
  path: string;
  title?: string;
  content: string;
  outputPath?: string;
  outputFolder?: string;
  detailMode?: KnotDetailMode;
  outputMode?: KnotOutputMode;
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
  rootNotePath?: string;
  artifacts?: string[];
  treeSummary?: {
    created: number;
    updated: number;
    unchanged: number;
  };
};

export type WorkspaceSettings = {
  baseDir: string;
  vaultDir: string;
  inboxDir: string;
  provider: string;
  detailMode: string;
  outputMode?: string;
};
