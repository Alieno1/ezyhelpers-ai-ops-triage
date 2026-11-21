"use client";

import React, { createContext, useContext, useState } from "react";
import type { DatasetName } from "@/lib/types";

interface DatasetCtx {
  dataset: DatasetName;
  setDataset: (d: DatasetName) => void;
}

const DatasetContext = createContext<DatasetCtx>({
  dataset: "supplied",
  setDataset: () => {},
});

export function DatasetProvider({ children }: { children: React.ReactNode }) {
  const [dataset, setDataset] = useState<DatasetName>("supplied");
  return <DatasetContext.Provider value={{ dataset, setDataset }}>{children}</DatasetContext.Provider>;
}

export function useDataset() {
  return useContext(DatasetContext);
}

