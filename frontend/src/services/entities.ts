import type { Building, EnergySource, StorageSystem, TransmissionLine } from "../types";
import { createEntityService } from "./entityService";

export const sourcesService = createEntityService<EnergySource>("sources");
export const storageService = createEntityService<StorageSystem>("storage");
export const buildingsService = createEntityService<Building>("buildings");
export const linesService = createEntityService<TransmissionLine>("lines");
