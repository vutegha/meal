/**
 * Contrat entre les types écrits à la main (api.ts) et ceux générés depuis l'OpenAPI de l'API
 * (schema.gen.ts, `npm run api:generate`) : si le serveur change un champ, `tsc` échoue ici.
 */
import type * as api from "./api";
import type { components } from "./schema.gen";

type S = components["schemas"];

/** Les deux types décrivent les mêmes champs, avec des types compatibles dans les deux sens. */
type Same<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false;
/** Le type écrit à la main est une vue plus précise du type généré (enums, unions). */
type Refines<A, B> = [A] extends [B] ? true : false;
type Check<T extends true> = T;

export type Contract = [
  Check<Refines<api.Organization, S["OrganizationOut"]>>,
  Check<Refines<api.Project, S["ProjectOut"]>>,
  Check<Refines<api.Indicator, S["IndicatorOut"]>>,
  Check<Refines<api.CollectionForm, S["FormOut"]>>,
  Check<Refines<api.Submission, S["SubmissionOut"]>>,
  Check<Refines<api.FormSummary, S["FormSummary"]>>,
  Check<Refines<api.Evidence, S["EvidenceOut"]>>,
  Check<Refines<api.SearchHit, S["SearchHit"]>>,
  Check<Same<keyof api.Project, keyof S["ProjectOut"]>>,
  Check<Same<keyof api.Indicator, keyof S["IndicatorOut"]>>,
  Check<Same<keyof api.CollectionForm, keyof S["FormOut"]>>,
  Check<Same<keyof api.Evidence, keyof S["EvidenceOut"]>>,
  Check<Same<keyof api.SearchHit, keyof S["SearchHit"]>>,
];
