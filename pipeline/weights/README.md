# Model weights drop folder

Place `xview2_1st_weights.zip` here and unzip it. Expected contents: a set of
`*_loc_*` (localization) and `*_cls_*` (damage classification) checkpoints from
the xView2 1st-place solution (se_resnext50 / dpn92 / resnet34 / senet154 U-Nets).

## Where to get it

The original host (`vdurnov.s3.amazonaws.com/xview2_1st_weights.zip`) now returns
AccessDenied. Working alternatives:

1. Wayback Machine (open in a normal browser):
   https://web.archive.org/web/20201212123547id_/https://vdurnov.s3.amazonaws.com/xview2_1st_weights.zip
   (older snapshot: .../web/20200904125854id_/...)
2. Any xView2 GPU box / teammate who already has the file.

Then: `cd pipeline/weights && unzip xview2_1st_weights.zip`
