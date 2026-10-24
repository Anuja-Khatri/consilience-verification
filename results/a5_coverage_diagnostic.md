# A5.1 coverage diagnostic (strict matching vs consensus filtering)

Windowed approved denominator: 31 (IIT+GNWT first-pass).
Consensus (≥4/5) recovered: 8/31 (0.258).

## Per-run (PRE-consensus) windowed coverage
- arm (a) live: mean 0.394, min 0.323, max 0.452  (runs: 0.387, 0.452, 0.323, 0.355, 0.452)
- arm (d) conf: mean 0.406, min 0.323, max 0.452  (runs: 0.419, 0.323, 0.419, 0.452, 0.419)

Reading: single runs recover ~39% of windowed approved; consensus (≥4/5) keeps 26%. The gap is consensus FILTERING (claims present in <4 runs are dropped), not strict field matching.

## Unrecovered windowed approved claims (23)
| approved_id | theory | approved (et/axis/pol/value) | nearest extracted | failed field(s) |
|---|---|---|---|---|
| iit_c003 | iit | constraint/computability/asserts/`non_computable_by_function_alone` | constraint/computability/asserts/`non_computable_by_function_alone` |  |
| iit_c004 | iit | state/mechanism/asserts/`phi_structure_state_dependent` | field/mechanism/asserts/`phi_structure_not_substrate_state` | entity_type |
| iit_c007 | iit | constraint/mechanism/asserts/`irreducible_integrated_information_required` | constraint/mechanism/asserts/`irreducible_integration_required` |  |
| iit_c010 | iit | constraint/locus/asserts/`single_maximal_complex` | system/locus/asserts/`maximal_irreducible_complex` | entity_type |
| iit_c012 | iit | emergent_property/identity_relation/asserts/`phi_structure_equals_experience` | invariant/identity_relation/asserts/`experience_equals_phi_structure` | entity_type |
| iit_c013 | iit | observer/fundamentality/asserts/`intrinsic_perspective_primary` | observer/locus/asserts/`intrinsic_not_observer_relative` | axis |
| iit_c016 | iit | invariant/architecture/asserts/`integrated_irreducible` | invariant/identity_relation/asserts/`experience_identical_to_maximally_irreducible_conceptual_structure` | axis |
| iit_n002 | iit | substrate/computability/asserts/`simulation_not_conscious_von_neumann` | substrate/substrate_dependence/asserts/`substrate_dependent` | axis, value_family |
| iit_n005 | iit | measurement/observable_commitment/asserts/`empirically_measurable_via_causal_perturbation` | measurement/observable_commitment/asserts/`quantitative_phi_measure` |  |
| iit_n006 | iit | constraint/architecture/asserts/`requires_integrated_recurrent_architecture` | constraint/architecture/asserts/`integrated_recurrent_required` |  |
| iit_n007 | iit | boundary/locus/asserts/`maximal_irreducible_complex` | boundary/locus/asserts/`maximal_irreducibility_demarcates_conscious_complex` |  |
| iit_t001 | iit | measurement/observable_commitment/asserts/`perturbational_complexity_index` | measurement/observable_commitment/asserts/`quantitative_phi_measure` | value_family |
| iit_t002 | iit | substrate/locus/asserts/`posterior_hot_zone` | substrate/locus/asserts/`cerebral_cortex` | value_family |
| gnwt_c004 | gnwt | information/observable_commitment/asserts/`access_consciousness_primary` | constraint/observable_commitment/asserts/`access_consciousness_not_phenomenal` | entity_type |
| gnwt_c008 | gnwt | constraint/connectivity/asserts/`global_workspace_connectivity_required` | constraint/connectivity/asserts/`recurrent_long_range` | value_family |
| gnwt_c012 | gnwt | substrate/substrate_dependence/asserts/`neuroanatomically_grounded` | substrate/substrate_dependence/asserts/`substrate_dependent` | value_family |
| gnwt_c013 | gnwt | system/architecture/asserts/`global_neuronal_workspace_broadcast` | system/architecture/asserts/`global_neuronal_workspace_broadcasting_architecture` |  |
| gnwt_c015 | gnwt | process/mechanism/asserts/`attention_access_dissociation` | process/mechanism/asserts/`global_information_access` |  |
| gnwt_c017 | gnwt | constraint/architecture/asserts/`recurrent_feedback_required` | constraint/connectivity/asserts/`recurrent_long_range` | axis |
| gnwt_c020 | gnwt | substrate/architecture/asserts/`long_distance_cortical_network_prefrontal_parietal` | substrate/architecture/asserts/`long_range_cortical_network` |  |
| gnwt_c022 | gnwt | measurement/observable_commitment/asserts/`neural_correlates_of_conscious_access` | measurement/observable_commitment/asserts/`multi_signature_neural_correlates` |  |
| gnwt_c025 | gnwt | emergent_property/temporal_profile/asserts/`gradual_buildup` | emergent_property/temporal_profile/asserts/`late_300_500ms_global_ignition` | value_family |
| gnwt_n004 | gnwt | system/architecture/asserts/`dual_component_C1_C2` | system/architecture/asserts/`global_neuronal_workspace_broadcasting_architecture` | value_family |
