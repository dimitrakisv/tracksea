# Darwin Core Mapping

## Purpose

TrackSea uses a user-friendly domain model internally and maps eligible records to Darwin Core-compatible exports for research and biodiversity data exchange.

Users should never need to understand Darwin Core terminology to create an observation.

## Design rules

- TrackSea domain entities remain authoritative for application behavior.
- Darwin Core is an export and interoperability layer.
- Mapping logic lives in a dedicated adapter.
- Sensitive or private coordinates are never exported without explicit policy and authorization.
- Historical identifications remain preserved even when the accepted taxon changes.
- Exported fields must document whether they are original, derived, generalized, or omitted.

## Initial field mapping

| TrackSea field | Darwin Core term | Notes |
|---|---|---|
| `Observation.occurrence_id` | `occurrenceID` | Stable public identifier |
| `Observation.observed_at` | `eventDate` | ISO 8601 value |
| `Observation.latitude_public` | `decimalLatitude` | Public or generalized value only |
| `Observation.longitude_public` | `decimalLongitude` | Public or generalized value only |
| `Observation.coordinate_uncertainty_meters` | `coordinateUncertaintyInMeters` | Device or derived uncertainty |
| `Observation.locality_text` | `locality` | Human-readable locality |
| `Observation.country_code` | `countryCode` | ISO country code where known |
| `Observation.observation_method` | `samplingProtocol` | For example snorkelling, fishing, or swimming |
| `Observation.quantity` | `organismQuantity` | Optional |
| `Observation.quantity_type` | `organismQuantityType` | For example individuals |
| `Observation.life_stage` | `lifeStage` | Optional controlled value |
| `Observation.sex` | `sex` | Optional controlled value |
| `Observation.behaviour` | `behavior` | Optional |
| `Observation.occurrence_status` | `occurrenceStatus` | Usually present for a sighting |
| `Observation.depth_min_meters` | `minimumDepthInMeters` | Optional |
| `Observation.depth_max_meters` | `maximumDepthInMeters` | Optional |
| `Observation.habitat` | `habitat` | Optional |
| `Observation.notes` | `occurrenceRemarks` | User-provided remarks |
| accepted `Taxon.scientific_name` | `scientificName` | Based on qualifying identification state |
| `Taxon.rank` | `taxonRank` | Species, genus, family, and so on |
| `Taxon.external_source_id` | `taxonID` | Source-specific identifier when suitable |
| accepted identification status | `identificationVerificationStatus` | Derived from TrackSea status |
| observer display attribution | `recordedBy` | Subject to privacy policy |
| media URLs | `associatedMedia` | Only redistributable media |
| observation license | `license` | Data license |
| TrackSea record type | `basisOfRecord` | Normally `HumanObservation` |

## Identification selection for export

The exporter must select a taxon according to a documented rule, such as:

1. expert-verified identification;
2. otherwise, qualifying community identification;
3. otherwise, the best available higher-rank identification;
4. otherwise, leave taxonomic fields empty.

The observer's original suggestion must not automatically become the exported accepted identification.

## Coordinate privacy

The exporter uses only the public coordinate representation.

Possible export behavior includes:

- exact public coordinates;
- rounded coordinates;
- randomized coordinates within a configured radius;
- region-only locality; or
- omitted coordinates for sensitive records.

The private coordinates remain outside the Darwin Core adapter unless an authorized private export is explicitly implemented later.

## Media

Only media with compatible licensing and visibility may be included in `associatedMedia`.

The export should provide processed media URLs rather than original files that may contain private metadata.

## Provenance

Future exports should include sufficient provenance to understand:

- the TrackSea record identifier;
- export time and version;
- mapping-rule version;
- taxonomic source;
- coordinate-generalization policy;
- identification status; and
- applicable licenses.

## MVP implementation boundary

During the first engineering sprint, TrackSea only needs:

- this documented mapping;
- domain fields that can support it; and
- tests ensuring privacy-sensitive fields are not accidentally mapped.

A full Darwin Core Archive and external publishing integration are later deliverables.
