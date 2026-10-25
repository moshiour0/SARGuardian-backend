from __future__ import annotations
import numpy as np
import pytest
from tools.know_place.crown_mask_audit import CrownMaskAuditError,CROWN,EPSG,X0,Y0,DX,DY,endpoint_crop,geographic_mask

def test_published_rectangle_matches_pinned_grid_and_crop():
    rows=np.arange(2675,2748,dtype=float); cols=np.arange(2827,2907,dtype=float)
    x=X0+(cols+.5)*DX; y=Y0+(rows+.5)*DY
    geo=geographic_mask(x,y,EPSG,CROWN)
    extent=(85.49978731371755,85.56493164458077,28.265783121030417,28.317068471931638)
    crop=endpoint_crop(geo.shape,extent,CROWN)
    assert int(geo.sum())==323 and int(crop.sum())==323
    np.testing.assert_array_equal(geo,crop)

def test_endpoint_crop_known_searchsorted_example():
    got=endpoint_crop((4,4),(0,4,0,4),(1,1,3,3)); expected=np.zeros((4,4),bool); expected[1:3,1:3]=True
    np.testing.assert_array_equal(got,expected)

def test_geographic_mask_descending_y_and_inclusive_bounds():
    got=geographic_mask([.5,1.5,2.5],[2.5,1.5,.5],4326,(1,1,2,2))
    expected=np.zeros((3,3),bool); expected[1,1]=True
    np.testing.assert_array_equal(got,expected)

def test_reject_nonmonotonic_axis():
    with pytest.raises(CrownMaskAuditError,match="X_AXIS_NOT_STRICTLY_MONOTONIC"):
        geographic_mask([0,2,1],[0,1],4326,(0,0,2,1))

def test_reject_crown_outside_extent():
    with pytest.raises(CrownMaskAuditError,match="CROWN_OUTSIDE_OR_INVALID_EXTENT"):
        endpoint_crop((4,4),(0,4,0,4),(5,1,6,2))
