package ncats.stitcher.impl;

import java.io.*;
import java.util.*;
import java.util.zip.*;
import java.util.Base64;
import java.net.URL;
import java.sql.*;

import java.lang.reflect.Array;
import java.util.logging.Logger;
import java.util.logging.Level;
import java.security.DigestInputStream;

import com.typesafe.config.ConfigFactory;
import com.typesafe.config.Config;
import com.typesafe.config.ConfigValue;
import com.typesafe.config.ConfigValueType;
import com.typesafe.config.ConfigList;
import com.typesafe.config.ConfigObject;
import com.zaxxer.hikari.HikariDataSource;

import ncats.stitcher.*;
import static ncats.stitcher.StitchKey.*;

public class NCGCEntityFactory extends MoleculeEntityFactory {
    static final Logger logger =
        Logger.getLogger(NCGCEntityFactory.class.getName());
    
    HikariDataSource dsource = new HikariDataSource ();
    int count;
    int maxrows;
    
    public NCGCEntityFactory (String dir) throws IOException {
        super (dir);
    }

    public NCGCEntityFactory (File dir) throws IOException {
        super (dir);
    }

    public NCGCEntityFactory (GraphDb graphDb) throws IOException {
        super (graphDb);
    }

    @Override
    protected void init () {
        super.init();
        setIdField ("SampleId");
        setStrucField ("SMILES");
        add (N_Name, "SampleName");
        add (I_CID, "PubChemCID");
        add (I_SID, "PubChemSID");
        add (I_Code, "SampleId");
        add (I_Code, "Tox21Id");
        add (I_CAS, "CAS");
        add (T_Keyword, "ApprovalStatus");
        add (T_Keyword, "Library");
        add (T_Keyword, "Supplier");
    }

    String instrument (ResultSet rset, Map<String, Object> row)
        throws SQLException {
        row.clear();
        String sampleId = rset.getString("sample_id");  
        
        row.put("SampleId", sampleId);
        long cid = rset.getLong("pubchem_cid");
        if (!rset.wasNull()) row.put("PubChemCID", cid);
        long sid = rset.getLong("pubchem_sid");
        if (!rset.wasNull()) row.put("PubChemSID", sid);
        String smiles = rset.getString("smiles_iso");
        if (smiles != null) row.put("SMILES", smiles);
        String cas = rset.getString("cas");
        if (cas != null) row.put("CAS", cas);
        String moa = rset.getString("primary_moa");
        if (moa != null) row.put("MOA", moa);
        String status = rset.getString("approval_status");
        if (status != null) row.put("ApprovalStatus", status);
        String supl = rset.getString("supplier");
        if (supl != null) row.put("Supplier", supl);
        String suplId = rset.getString("supplier_id");
        if (suplId != null) row.put("SupplierId", suplId);
        String name = rset.getString("sample_name");
        if (name != null) row.put("SampleName", name);
        name = rset.getString("sample_name2");
        if (name != null)
            row.put("SampleName", Util.merge(row.get("SampleName"), name));
        String tox21 = rset.getString("tox21_id");
        if (tox21 != null) row.put("Tox21Id", tox21);
        return sampleId;
    }
    
    void register (Connection con) throws SQLException {
        PreparedStatement pstm = con.prepareStatement
            ("select sample_id,smiles_iso,sample_name,supplier,supplier_id,"
             +"pubchem_sid,pubchem_cid,cas,primary_moa,approval_status,"
             +"tox21_id,sample_name2 "
             +"from ncgc_sample "
             +"where smiles_iso is not null "
             +(maxrows > 0 ? "order by sample_id fetch first "
               +maxrows+" rows only":""));
        PreparedStatement pstm2 = con.prepareStatement
            ("select key,value from sample_annotation where sample_id = ?");
        ResultSet rset = pstm.executeQuery();
        Map<String, Object> row = new TreeMap<>();      
        while (rset.next()) {
            String sampleId = instrument (rset, row);
            
            System.out.println("+++++ "+sampleId+" "+(count+1)+" +++++");
            pstm2.setString(1, sampleId);
            ResultSet rs = pstm2.executeQuery();
            while (rs.next()) {
                String key = rs.getString(1);
                String val = rs.getString(2);
                switch (key) {
                case "library":
                    row.put("Library", Util.merge(row.get("Library"), val));
                    break;
                    
                case "compound.name.primary":
                    row.put("SampleName",
                            Util.merge(row.get("SampleName"), val));
                    break;
                    
                default:
                    logger.warning("Unknown sample annotation: "+key);
                }
            }
            rs.close();
            
            ncats.stitcher.Entity e = registerIfAbsent (row);
            if (e != null)
                ++count;
        }
        rset.close();
        pstm.close();
        pstm2.close();
    }
    
    public int register (String config, String username, String password)
        throws Exception {
        Config conf = ConfigFactory.parseReader
            (new InputStreamReader (new FileInputStream (config)));
        if (!conf.hasPath("source")) {
            throw new IllegalArgumentException
                ("Configuration contains no \"source\" definition!");
        }
                
        //System.out.println("source:"+source);
        if (conf.hasPath("cache")) {
            String cache = conf.getString("cache");
            setCache (cache);
        }

        Config source = conf.getConfig("source");
        if (!source.hasPath("name")) {
            throw new IllegalArgumentException
                ("Configuration contains no \"source.name\" definition!");
        }
        
        if (!source.hasPath("url")) {
            throw new IllegalArgumentException
                ("Configuration contains no \"source.url\" definition!");
        }

        if (source.hasPath("rows")) {
            maxrows = source.getInt("rows");
        }
                
        dsource.setJdbcUrl(source.getString("url"));
        dsource.setUsername(username);
        dsource.setPassword(password);

        count = 0;
        try (Connection con = dsource.getConnection()) {
            DataSource ds = getDataSourceFactory()
                .register(source.getString("name"));
            Integer instances = (Integer)ds.get(INSTANCES);
            if (instances != null && instances > 0) {
                logger.info("### Data source "+ds.getName()
                            +" has already been registered with "+instances
                            +" entities!");
            }
            setDataSource (ds);
            
            register (con);
            if (count > 0) {
                if (instances == null) {
                    instances = 0;
                    updateMeta (ds);
                }
                ds.set(INSTANCES, instances+count);
            }
            
            logger.info("$$$ "+count+" new entities registered "
                        +"for data source \""+ds+"\"");
        }
        catch (SQLException ex) {
            ex.printStackTrace();
        }
        
        return count;
    }

    public static void main (String[] argv) throws Exception {
        if (argv.length < 4) {
            System.err.println("Usage: " + NCGCEntityFactory.class.getName()
                    + " DBDIR CONFIG USERNAME PASSWORD");
            System.exit(1);
        }
        
        NCGCEntityFactory ncgc = new NCGCEntityFactory (argv[0]);
        try {
            int count = ncgc.register(argv[1], argv[2], argv[3]);
        }
        finally {
            ncgc.shutdown();
        }
    }
}
